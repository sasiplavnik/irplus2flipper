from io import BufferedReader
from bs4 import BeautifulSoup
import glob
from typing import List, Any
import binascii
import struct
import os
from yamahanec2lirc import yamahanec_code_to_lirc


def replace_nonascii(text: str):
    return ''.join([i if ord(i) < 128 else '' for i in text])


# https://github.com/emilsoman/pronto_broadlink
def pronto2lirc(pronto: str) -> List[str]:
    codes = []
    for s in pronto.split(" "):
        codes.append(int(s, 16))
    if codes[0] != 0:
        raise ValueError('Pronto code should start with 0000')
    if len(codes) != 4 + 2 * (codes[2] + codes[3]):
        raise ValueError('Number of pulse widths does not match the preamble')
    frequency = 1 / (codes[1] * 0.241246)
    return [str(int(round(code / frequency))) for code in codes[4:]]


class Command():
    name: str
    type: str
    protocol: str
    address: str
    data: str
    frequency: int
    duty_cycle: float
    device: Any  # Device()

    def __init__(
            self,
            **kwargs) -> None:
        self.device = kwargs.get("device", None)
        self.name = kwargs.get("name", "")
        self.format = self.device.format
        self.frequency = self.device.frequency
        data = kwargs.get("data", "")
        if self.format == "WINLIRC_RC5":
            self.type_ = "parsed"
            self.protocol = "RC5"
            command_int = int(data, 16)
            command = command_int & 0xff
            address = (command_int & 0xff00) >> 8
            command_str = binascii.hexlify(
                struct.pack("<I", command), sep=" ").upper()
            add_str = binascii.hexlify(
                struct.pack("<I", address), sep=" ").upper()
            self.command = command_str.decode('ascii')
            self.address = add_str.decode('ascii')
            return
        elif self.format in ["WINLIRC_NEC1", "WINLIRC_NECx1"]:
            self.type_ = "parsed"
            self.protocol = "NECext"
            data_split = data.split(" ")
            address = int(data_split[0], 16)
            command = int(data_split[1], 16)
            command_str = binascii.hexlify(
                struct.pack("<I", command), sep=" ").upper()
            add_str = binascii.hexlify(
                struct.pack("<I", address), sep=" ").upper()
            self.command = command_str.decode('ascii')
            self.address = add_str.decode('ascii')
            return
        elif self.format == "WINLIRC_RC6":
            self.type_ = "parsed"
            self.protocol = "RC6"
            data_split = data.split(" ")
            address = int(data_split[0], 16)
            command = int(data_split[1], 16)
            command_str = binascii.hexlify(
                struct.pack("<I", command), sep=" ").upper()
            add_str = binascii.hexlify(
                struct.pack("<I", address), sep=" ").upper()
            self.command = command_str.decode('ascii')
            self.address = add_str.decode('ascii')
            return
        elif self.format in ["WINLIRC_RAW", "WINLIRC_RAW_T"]:
            self.type_ = "raw"
            self.protocol = ""
            self.duty_cycle = 0.33
            self.data = data
            return
        elif self.format == "PRONTO_HEX":
            self.type_ = "raw"
            self.protocol = ""
            self.duty_cycle = 0.33
            self.data = " ".join(pronto2lirc(data))
            return
        elif self.format == "YAMAHA_NEC_HEX":
            self.type_ = "parsed"
            self.protocol = "NECext"
            # https://github.com/nobbin/infrared/blob/master/convert/yamahanec2lirc.py
            command_int = yamahanec_code_to_lirc(data)
            command = command_int & 0xffff
            address = (command_int & 0xffff0000) >> 16
            command_str = binascii.hexlify(
                struct.pack("<I", command), sep=" ").upper()
            add_str = binascii.hexlify(
                struct.pack("<I", address), sep=" ").upper()
            self.command = command_str.decode('ascii')
            self.address = add_str.decode('ascii')
            return
        elif self.format == "XIAOMI_IR":
            self.type_ = "parsed"
            self.protocol = "NEC"
            data_split = data.split(" ")
            address = int(data_split[0], 16)
            command = int(data_split[1], 16)
            command_str = binascii.hexlify(
                struct.pack("<I", command), sep=" ").upper()
            add_str = binascii.hexlify(
                struct.pack("<I", address), sep=" ").upper()
            self.command = command_str.decode('ascii')
            self.address = add_str.decode('ascii')
            return
        else:
            raise NotImplementedError(f"{self.format} is not implemented")


class Device():
    filename: str
    manufacturer: str
    model: str
    format: str
    commands: List[Command]
    frequency: int

    def __init__(self, **kwargs) -> None:
        self.filename = kwargs.get("filename", "")
        self.manufacturer = kwargs.get("manufacturer", "")
        self.model = kwargs.get("model", "").replace("/", "-")
        self.format = kwargs.get("format", "")
        self.frequency = kwargs.get("frequency", 38000)
        self.commands = []
        return


def generate_flipper_ir_file(device: Device) -> str:
    template = "Filetype: IR signals file\n"
    template += "Version: 1\n"
    template += "#\n"
    template += f"# {device.manufacturer} {device.model}\n"
    template += f"# Autogenerated from {device.filename}\n"
    for command in device.commands:
        template += "#\n"
        template += f"name: {command.name}\n"
        if command.protocol != "":
            template += f"protocol: {command.protocol}\n"
            template += f"address: {command.address}\n"
            template += f"command: {command.command}\n"
        else:
            template += f"type: {command.type_}\n"
            template += f"frequency: {command.frequency}\n"
            template += f"duty_cycle: {command.duty_cycle}\n"
            template += f"data: {command.data}\n"
    return template


def get_device(f: BufferedReader) -> Device:
    soup = BeautifulSoup(f, 'lxml')
    device = soup.find("device")
    if device is None:
        linked = soup.find("linked")
        if linked is not None:
            asset_path = linked.attrs.get("asset", None)
            ff = open(f"ircodes/{asset_path}", "rb")
            # Recursion goes brrr
            device = get_device(ff)
            return device
    manufacturer = device.attrs.get("manufacturer", "None")
    model = device.attrs.get("model", "None")
    format = device.attrs.get("format", "None")
    frequency = device.attrs.get("frequency", 38000)

    device_obj = Device(
        filename=f.name, manufacturer=manufacturer, model=model, format=format, frequency=frequency)

    for button in soup.findAll("button"):
        command_name = button.attrs.get("alt", None)
        if command_name is None:
            command_name = button.attrs.get("label", None)
        if command_name is not None:
            command_name = replace_nonascii(command_name)
            command_name = command_name.strip()
        else:
            continue
        if (command_name.isascii() is not True) or len(command_name) == 0:
            command_name = "Unknown"
        command_data = button.text
        try:
            command = Command(
                device=device_obj,
                name=command_name,
                data=command_data,
                format=format)
            device_obj.commands.append(command)
        except Exception as e:
            # print(e)
            pass
    return device_obj


if __name__ == "__main__":
    for filename in glob.iglob("ircodes/**/*.xml", recursive=True):
        f = open(filename, "rb")
        device = get_device(f)
        f.close()
        if (device is None) or (len(device.commands) == 0):
            continue
        flipper_str = generate_flipper_ir_file(device)
        os.makedirs(f"generated/{device.manufacturer}", exist_ok=True)
        with open(f"generated/{device.manufacturer}/{device.model}.ir", "wb") as fi:
            fi.write(flipper_str.encode("ascii"))
            print(f"Done at {fi.name}")
    print()
