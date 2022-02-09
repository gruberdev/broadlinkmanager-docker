# region Importing

import os, json, subprocess, time, broadlink, argparse, datetime, re, shutil, uvicorn, socket
from os import environ, path
from json import dumps
from broadlink.exceptions import ReadError, StorageError
from subprocess import call
from loguru import logger
from fastapi import FastAPI, Request, File, Form, UploadFile
from fastapi.responses import UJSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from starlette_exporter import PrometheusMiddleware, handle_metrics

# Use to disable Google analytics code
ENABLE_GOOGLE_ANALYTICS = os.getenv("ENABLE_GOOGLE_ANALYTICS")
# endregion

#Get Lan IP
def GetLocalIP():
    p = subprocess.Popen("hostname -I | awk '{print $1}'", stdout=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    p_status = p.wait()
    ip = re.findall(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", str(output))[0]
    logger.debug(ip)
    return str(ip)

local_ip_address = GetLocalIP()

# Get version from version file for dynamic change
def GetVersionFromFle():
    with open("VERSION","r") as version:
        v = version.read()
        return v

# Tags metadata for swagger docs
tags_metadata = [
    {
        "name": "Html Pages",
        "description": "Returns HTML pages",
    },
    {
        "name": "Commands",
        "description": "Learn / Send RF or IR commands",
 
        },
     {
        "name": "Devices",
        "description": "Scan for devices on the network or load/save from/to file",
 
        },
    
]



# region Parsing Default arguments for descovery

parser = argparse.ArgumentParser(fromfile_prefix_chars='@')
parser.add_argument("--timeout", type=int, default=5,
                    help="timeout to wait for receiving discovery responses")
parser.add_argument("--ip", default=local_ip_address,
                    help="ip address to use in the discovery")
parser.add_argument("--dst-ip", default="255.255.255.255",
                    help="destination ip address to use in the discovery")
args = parser.parse_args()

# endregion

# region Declaring Flask app

app = FastAPI(title="Apprise API", description="Send multi channel notification using single endpoint", version=GetVersionFromFle(), openapi_tags=tags_metadata,contact={"name":"Tomer Klein","email":"tomer.klein@gmail.com","url":"https://github.com/t0mer/apprise-api-bridge"})
logger.info("Configuring app")
app.mount("/dist", StaticFiles(directory="dist"), name="dist")
app.mount("/js", StaticFiles(directory="dist/js"), name="js")
app.mount("/css", StaticFiles(directory="dist/css"), name="css")
app.mount("/img", StaticFiles(directory="dist/img"), name="css")
app.mount("/webfonts", StaticFiles(directory="dist/webfonts"), name="css")
templates = Jinja2Templates(directory="templates/")
app.add_middleware(PrometheusMiddleware)
app.add_route("/metrics", handle_metrics)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# endregion

# region Global Properties
_continu_to_sweep = False
_rf_sweep_message = ''
_rf_sweep_status = False

TICK = 32.84
IR_TOKEN = 0x26
TIMEOUT = 30

# endregion

# region Broadlink Helper Methods


def get_analytics_code():
    try:
        if ENABLE_GOOGLE_ANALYTICS=="True":
            analytics_file_path = os.path.join(app.root_path, 'templates', 'analytics_code.html')
            f = open(analytics_file_path, "r")
            content = f.read()
            f.close()
            logger.info('Content: ' + content)
            return content
        else:
            return ''
    except Exception as e:
        logger.error(str(e))
        return ''


analytics_code = get_analytics_code()

def getDeviceName(deviceType):
    name = {
        0x2711: "SP2",
        0x2719: "Honeywell SP2",
        0x7919: "Honeywell SP2",
        0x271a: "Honeywell SP2",
        0x791a: "Honeywell SP2",
        0x2720: "SPMini",
        0x753e: "SP3",
        0x7D00: "OEM branded SP3",
        0x947a: "SP3S",
        0x9479: "SP3S",
        0x2728: "SPMini2",
        0x2733: "OEM branded SPMini",
        0x273e: "OEM branded SPMini",
        0x7530: "OEM branded SPMini2",
        0x7546: "OEM branded SPMini2",
        0x7918: "OEM branded SPMini2",
        0x7D0D: "TMall OEM SPMini3",
        0x2736: "SPMiniPlus",
        0x2712: "RM2",
        0x2737: "RM Mini",
        0x273d: "RM Pro Phicomm",
        0x2783: "RM2 Home Plus",
        0x277c: "RM2 Home Plus GDT",
        0x272a: "RM2 Pro Plus",
        0x2787: "RM2 Pro Plus2",
        0x279d: "RM2 Pro Plus3",
        0x27a9: "RM2 Pro Plus_300",
        0x278b: "RM2 Pro Plus BL",
        0x2797: "RM2 Pro Plus HYC",
        0x27a1: "RM2 Pro Plus R1",
        0x27a6: "RM2 Pro PP",
        0x278f: "RM Mini Shate",
        0x27c2: "RM Mini 3",
        0x2714: "A1",
        0x4EB5: "MP1",
        0x4EF7: "Honyar oem mp1",
        0x4EAD: "Hysen controller",
        0x2722: "S1 (SmartOne Alarm Kit)",
        0x4E4D: "Dooya DT360E (DOOYA_CURTAIN_V2)",
        0x51da: "RM4 Mini",
        0x5f36: "RM Mini 3",
        0x6026: "RM4 Pro",
	0x6070: "RM4c Mini",
        0x61a2: "RM4 Pro",
        0x610e: "RM4 Mini",
        0x610f: "RM4c",
        0x62bc: "RM4 Mini",
        0x62be: "RM4c Mini",
        0x51E3: "BG Electrical Smart Power Socket",
        0x60c8: "RGB Smart Bulb",
        0x6539: "RM4c Mini",
        0x653a: "RM4 Mini",
	0x653c: "RM4 Pro",
	0x649b: "RM4 Pro",
        0x6184: "RM4C mini",
        0x648d: "RM4 Mini",
	0x5209: "RM4 TV Mate",
    0x27C3: "RM pro+",
    0x27C7: "RM mini 3",
    0x27CC: "RM mini 3",
    0x27D0: "RM mini 3",
    0x27D3: "RM mini 3",
    0x27DC: "RM mini 3",
    0x6507: "RM mini 3",
    0x6508: "RM mini 3",

    }
    return name.get(deviceType, "Not Supported")


def auto_int(x):
    return int(x, 0)

def to_microseconds(bytes):
    result = []
    #  print bytes[0] # 0x26 = 38for IR
    index = 4
    while index < len(bytes):
        chunk = bytes[index]
        index += 1
        if chunk == 0:
            chunk = bytes[index]
            chunk = 256 * chunk + bytes[index + 1]
            index += 2
        result.append(int(round(chunk * TICK)))
        if chunk == 0x0d05:
            break
    return result

def durations_to_broadlink(durations):
    result = bytearray()
    result.append(IR_TOKEN)
    result.append(0)
    result.append(len(durations) % 256)
    result.append(len(durations) / 256)
    for dur in durations:
        num = int(round(dur / TICK))
        if num > 255:
            result.append(0)
            result.append(num / 256)
        result.append(num % 256)
    return result

def format_durations(data):
    result = ''
    for i in range(0, len(data)):
        if len(result) > 0:
            result += ' '
        result += ('+' if i % 2 == 0 else '-') + str(data[i])
    return result

def parse_durations(str):
    result = []
    for s in str.split():
        result.append(abs(int(s)))
    return result

def initDevice(dtype, host, mac):
    dtypeTmp = dtype
    if dtypeTmp == '0x6539':
	    dtypeTmp = '0x610F'
    _dtype = int(dtypeTmp, 0)
    _host = host
    _mac = bytearray.fromhex(mac)
    return broadlink.gendevice(_dtype, (_host, 80), _mac)

def GetDevicesFilePath():
    return os.path.join(app.root_path, 'data', 'devices.json')

def writeXml(_file):
    root = ET.Element("root")
    doc = ET.SubElement(root, "doc")
    ET.SubElement(doc, "field1", name="blah").text = "some value1"
    ET.SubElement(doc, "field2", name="asdfasd").text = "some vlaue2"
    tree = ET.ElementTree(root)
    tree.write(_file)


@app.get('/', tags=["Html Pages"])
def devices(request: Request):
    return templates.TemplateResponse('index.html', context={'request': request,'analytics':analytics_code, 'version': GetVersionFromFle()})


@app.get('/generator', tags=["Html Pages"])
def generator(request: Request):
    return templates.TemplateResponse('generator.html', context={'request': request,'analytics':analytics_code, 'version': GetVersionFromFle()})


@app.get('/livolo', tags=["Html Pages"])
def livolo(request: Request):
    return templates.TemplateResponse('livolo.html', context={'request': request,'analytics':analytics_code, 'version': GetVersionFromFle()})


@app.get('/energenie', tags=["Html Pages"])
def energenie(request: Request):
    return templates.TemplateResponse('energenie.html', context={'request': request,'analytics':analytics_code, 'version': GetVersionFromFle()})


@app.get('/repeats', tags=["Html Pages"])
def repeats(request: Request):
    return templates.TemplateResponse('repeats.html', context={'request': request,'analytics':analytics_code, 'version': GetVersionFromFle()})


@app.get('/convert', tags=["Html Pages"])
def convert(request: Request):
    return templates.TemplateResponse('convert.html', context={'request': request,'analytics':analytics_code, 'version': GetVersionFromFle()})


@app.get('/about', tags=["Html Pages"])
def about(request: Request):
    return templates.TemplateResponse('about.html', context={'request': request,'analytics':analytics_code, 'version': GetVersionFromFle()})


@app.get('/temperature', tags=["Commands"])
def temperature(request: Request):
    logger.info("Getting temperature for device: " + request.args.get('host'))
    dev = initDevice(request.args.get('type'), request.args.get(
        'host'), request.args.get('mac'))
    dev.auth()
    try:
        logger.info("Success Getting temperature for device: " + request.args.get('host'))
        return JSONResponse('{"data":"'+dev.check_temperature()+'","success":"1"}')
    except:
        logger.info("Error Getting temperature for device: " + request.args.get('host'))
        return JSONResponse('{"data":"Method Not Supported","success":"0"}')


@app.get('/ir/learn', tags=["Commands"])
def learnir(request: Request, mac: str = "", host: str = "", type: str = "", command: str =""):
    logger.info("Learning IR Code for device: " + host)
    dev = initDevice(type, host, mac)
    dev.auth()
    logger.info("Entering IR Learning Mode")
    dev.enter_learning()
    start = time.time()
    while time.time() - start < TIMEOUT:
        time.sleep(1)
        try:
            data = dev.check_data()
        except (ReadError, StorageError):
            continue
        else:
            break
    else:
        logger.error("No IR Data")
        return JSONResponse('{"data":"","success":0,"message":"No Data Received"}')
    learned = ''.join(format(x, '02x') for x in bytearray(data))
    logger.info("IR Learn success")
    return JSONResponse('{"data":"' + learned + '","success":1,"message":"IR Data Received"}')

# Send IR/RF
@app.get('/command/send', tags=["Commands"])
def command(request: Request, mac: str = "", host: str = "", type: str = "", command: str =""):
    logger.info("Sending Command (IR/RF) using device: " + host)
    dev = initDevice(type, host, mac)
    logger.info("Sending command: " + command)
    dev.auth()
    try:
        dev.send_data(bytearray.fromhex(''.join(command)))
        logger.info("Command sent successfully")
        return JSONResponse('{"data":"","success":1,"message":"Command sent successfully"}')
    except Exception as ex:
        logger.info("Error in sending command, the exception was: " + str(ex))
        return JSONResponse('{"data":"","success":0,"message":"Error occurred while Sending command!"}')


# Learn RF
@app.get('/rf/learn', tags=["Commands"])
def sweep(request: Request, mac: str = "", host: str = "", type: str = "", command: str =""):
    global _continu_to_sweep
    global _rf_sweep_message
    global _rf_sweep_status
    _continu_to_sweep = False
    _rf_sweep_message = ''
    _rf_sweep_status = False
    logger.info("Device:" + host + " entering RF learning mode" )
    dev = initDevice(type, host,mac)
    dev.auth()
    logger.info("Device:" + host + " is sweeping for frequency")
    dev.sweep_frequency()
    _rf_sweep_message = "Learning RF Frequency, press and hold the button to learn..."
    start = time.time()
    while time.time() - start < TIMEOUT:
        time.sleep(1)
        if dev.check_frequency():
            break
    else:
        logger.error("Device:" + host + " RF Frequency not found!")
        _rf_sweep_message = "RF Frequency not found!"
        dev.cancel_sweep_frequency()
        return JSONResponse('{"data":"RF Frequency not found!","success":0}')

    _rf_sweep_message = "Found RF Frequency - 1 of 2!"
    logger.info("Device:" + host + " Found RF Frequency - 1 of 2!")
    time.sleep(1)
    _rf_sweep_message = "You can now let go of the button"
    logger.info("You can now let go of the button")
    _rf_sweep_status = True
    while _continu_to_sweep == False:
        _rf_sweep_message = "Click The Continue button"

    _rf_sweep_message = "To complete learning, single press the button you want to learn"
    logger.info("To complete learning, single press the button you want to learn")
    _rf_sweep_status = False
    logger.error("Device:" +host + " is searching for RF packets!")
    dev.find_rf_packet()
    start = time.time()
    while time.time() - start < TIMEOUT:
        time.sleep(1)
        try:
            data = dev.check_data()
        except (ReadError, StorageError):
            continue
        else:
            break
    else:
        logger.error("Device:" + host + " No Data Found!")
        _rf_sweep_message = "No Data Found"
        return JSONResponse('{"data":"No Data Found"}')

    _rf_sweep_message = "Found RF Frequency - 2 of 2!"
    logger.info("Device:" + host + " Found RF Frequency - 2 of 2!")
    learned = ''.join(format(x, '02x') for x in bytearray(data))
    _rf_sweep_message = "RF Scan Completed Successfully"
    logger.info("Device:" + host + " RF Scan Completed Successfully")
    time.sleep(1)
    return JSONResponse('{"data":"' + learned + '"}')

# Get RF Learning state

@app.get('/rf/status', tags=["Commands"])
def rfstatus(request: Request):
    global _continu_to_sweep
    global _rf_sweep_message
    global _rf_sweep_status
    return JSONResponse('{"_continu_to_sweep":"' + str(_continu_to_sweep) + '","_rf_sweep_message":"' + _rf_sweep_message + '","_rf_sweep_status":"' + str(_rf_sweep_status) + '" }')

# Continue with RF Scan
@app.get('/rf/continue', tags=["Commands"])
def rfcontinue(request: Request):
    global _continu_to_sweep
    global _rf_sweep_status
    _rf_sweep_status = True
    _continu_to_sweep = True
    return JSONResponse('{"_continu_to_sweep":"' + str(_continu_to_sweep) + '","_rf_sweep_message":"' + _rf_sweep_message + '","_rf_sweep_status":"' + str(_rf_sweep_status) + '" }')


# Save Devices List to json file

@app.post('/devices/save', tags=["Devices"])
async def save_devices_to_file(request: Request):
    data = await request.json()
    logger.info("Writing devices to file")
    try:
        with open(GetDevicesFilePath(), 'w') as f:
            f.write(str(data).replace("'", "\""))
        logger.info("Finished writing devices to file")
        return JSONResponse('{"success":1}')
    except Exception as ex:
        logger.error(
            "Writing devices to file faild has faild with the following exception: " + str(ex))
        return JSONResponse('{"success":0}')

# Load Devices from json file


@app.get('/devices/load', tags=["Devices"])
def load_devices_from_file(request: Request):
    try:
        logger.info("Reading devices from file")
        time.sleep(3)
        f = open(GetDevicesFilePath(), "r")
        return JSONResponse(f.read().replace("'", "\""))
    except Exception as ex:
        logger.error(
            "Loading devices from file has faild with the following exception: " + str(ex))
        return JSONResponse('{"success":0}')

# Search for devices in the network


@app.get('/autodiscover', tags=["Devices"])
def search_for_devices(request: Request,freshscan: str = "1"):
    _devices = ''
    if path.exists(GetDevicesFilePath()) and freshscan != "1":
        return load_devices_from_file(request)
    else:
        logger.info("Searcing for devices...")
        _devices = '['
        devices = broadlink.discover(timeout=5, local_ip_address=local_ip_address, discover_ip_address="255.255.255.255")
        for device in devices:
            if device.auth():
                logger.info("New device detected: " + getDeviceName(device.devtype) + " (ip: " + device.host[0] +  ", mac: " + ''.join(format(x, '02x') for x in device.mac) +  ")")
                _devices = _devices + '{"name":"' + \
                    getDeviceName(device.devtype) + '",'
                _devices = _devices + '"type":"' + \
                    format(hex(device.devtype)) + '",'
                _devices = _devices + '"ip":"' + device.host[0] + '",'
                _devices = _devices + '"mac":"' + \
                    ''.join(format(x, '02x') for x in device.mac) + '"},'

        if len(_devices)==1:
            _devices = _devices + ']'
            logger.debug("No Devices Found " + str(_devices))
        else:
            _devices = _devices[:-1] + ']'
            logger.debug("Devices Found " + str(_devices))
        return JSONResponse(_devices)




@app.get('/device/ping', tags=["Devices"])
def get_device_status(request: Request, host: str=""):
    try:
        if host =="":
            logger.error("Host must be a valid ip or hostname")
            return JSONResponse('{"status":"Host must be a valid ip or hostname","success":"0"}')
        p = subprocess.Popen("fping -C1 -q "+ host +"  2>&1 | grep -v '-' | wc -l", stdout=subprocess.PIPE, shell=True)
        logger.debug(host)
        (output, err) = p.communicate()
        p_status = p.wait()
        logger.debug(str(output))
        status = re.findall('\d+', str(output))[0]
        if status=="1":
            return JSONResponse('{"status":"online","success":"1"}')
        else:
            return JSONResponse('{"status":"offline","success":"1"}')
    except Exception as e:
        logger.error("Error pinging "+ host + " Error: " + str(e))
        return JSONResponse('{"status":"Error pinging ' + host + '" ,"success":"0"}')

# endregion API Methods



# Start Application
if __name__ == '__main__':
    logger.info("Broadllink Manager is up and running")
    uvicorn.run(app, host="0.0.0.0", port=7020)
