import base64, curl_cffi, json, pytz, random, re, uuid
from browserforge.fingerprints import Screen, FingerprintGenerator
from browserforge.headers import HeaderGenerator
from datetime import datetime, timedelta, timezone
from time import sleep

import config, utils

import logging

logger = logging.getLogger(__name__)


time_origin = -1
data_build = ''
fp = None
window_keys = [0, "window", "self", "document", "name", "location", "customElements", "history", "navigation", "locationbar", "menubar", "personalbar", "scrollbars", "statusbar", "toolbar", "status", "closed", "frames", "length", "top", "opener", "parent", "frameElement", "navigator", "origin", "external", "screen", "innerWidth", "innerHeight", "scrollX", "pageXOffset", "scrollY", "pageYOffset", "visualViewport", "screenX", "screenY", "outerWidth", "outerHeight", "devicePixelRatio", "event", "clientInformation", "screenLeft", "screenTop", "styleMedia", "onsearch", "trustedTypes", "performance", "onappinstalled", "onbeforeinstallprompt", "crypto", "indexedDB", "sessionStorage", "localStorage", "onbeforexrselect", "onabort", "onbeforeinput", "onbeforematch", "onbeforetoggle", "onblur", "oncancel", "oncanplay", "oncanplaythrough", "onchange", "onclick", "onclose", "oncontentvisibilityautostatechange", "oncontextlost", "oncontextmenu", "oncontextrestored", "oncuechange", "ondblclick", "ondrag", "ondragend", "ondragenter", "ondragleave", "ondragover", "ondragstart", "ondrop", "ondurationchange", "onemptied", "onended", "onerror", "onfocus", "onformdata", "oninput", "oninvalid", "onkeydown", "onkeypress", "onkeyup", "onload", "onloadeddata", "onloadedmetadata", "onloadstart", "onmousedown", "onmouseenter", "onmouseleave", "onmousemove", "onmouseout", "onmouseover", "onmouseup", "onmousewheel", "onpause", "onplay", "onplaying", "onprogress", "onratechange", "onreset", "onresize", "onscroll", "onsecuritypolicyviolation", "onseeked", "onseeking", "onselect", "onslotchange", "onstalled", "onsubmit", "onsuspend", "ontimeupdate", "ontoggle", "onvolumechange", "onwaiting", "onwebkitanimationend", "onwebkitanimationiteration", "onwebkitanimationstart", "onwebkittransitionend", "onwheel", "onauxclick", "ongotpointercapture", "onlostpointercapture", "onpointerdown", "onpointermove", "onpointerrawupdate", "onpointerup", "onpointercancel", "onpointerover", "onpointerout", "onpointerenter", "onpointerleave", "onselectstart", "onselectionchange", "onanimationend", "onanimationiteration", "onanimationstart", "ontransitionrun", "ontransitionstart", "ontransitionend", "ontransitioncancel", "onafterprint", "onbeforeprint", "onbeforeunload", "onhashchange", "onlanguagechange", "onmessage", "onmessageerror", "onoffline", "ononline", "onpagehide", "onpageshow", "onpopstate", "onrejectionhandled", "onstorage", "onunhandledrejection", "onunload", "isSecureContext", "crossOriginIsolated", "scheduler", "alert", "atob", "blur", "btoa", "cancelAnimationFrame", "cancelIdleCallback", "captureEvents", "clearInterval", "clearTimeout", "close", "confirm", "createImageBitmap", "fetch", "find", "focus", "getComputedStyle", "getSelection", "matchMedia", "moveBy", "moveTo", "open", "postMessage", "print", "prompt", "queueMicrotask", "releaseEvents", "reportError", "requestAnimationFrame", "requestIdleCallback", "resizeBy", "resizeTo", "scroll", "scrollBy", "scrollTo", "setInterval", "setTimeout", "stop", "structuredClone", "webkitCancelAnimationFrame", "webkitRequestAnimationFrame", "chrome", "caches", "cookieStore", "ondevicemotion", "ondeviceorientation", "ondeviceorientationabsolute", "launchQueue", "sharedStorage", "documentPictureInPicture", "fetchLater", "getDigitalGoodsService", "getScreenDetails", "queryLocalFonts", "showDirectoryPicker", "showOpenFilePicker", "showSaveFilePicker", "originAgentCluster", "onpageswap", "onpagereveal", "credentialless", "fence", "speechSynthesis", "oncommand", "onscrollend", "onscrollsnapchange", "onscrollsnapchanging", "webkitRequestFileSystem", "webkitResolveLocalFileSystemURL", "__oai_SSR_HTML", "__reactRouterContext", "$RC", "__oai_SSR_TTI", "__reactRouterManifest", "__reactRouterVersion", "DD_RUM", "__REACT_INTL_CONTEXT__", "__STATSIG__", "regeneratorRuntime", "DD_LOGS", "__mobxInstanceCount", "__mobxGlobals", "_g", "__reactRouterRouteModules", "__reactRouterDataRouter", "__SEGMENT_INSPECTOR__", "MotionIsMounted", "_oaiHandleSessionExpired"]
document_keys = []
navigator_key_values = []


def performance_now():
    return get_datetime_now().timestamp() * 1000 - time_origin


def get_datetime_now():
    return datetime.now(pytz.utc).astimezone(pytz.timezone('US/Eastern'))


def fnv_hash(str):
    # function B6(e) {
    #     let t = 2166136261;
    #     for (let n = 0; n < e.length; n++)
    #         t ^= e.charCodeAt(n),
    #         t = Math.imul(t, 16777619) >>> 0;
    #     return t ^= t >>> 16,
    #     t = Math.imul(t, 2246822507) >>> 0,
    #     t ^= t >>> 13,
    #     t = Math.imul(t, 3266489909) >>> 0,
    #     t ^= t >>> 16,
    #     (t >>> 0).toString(16).padStart(8, "0")
    # }
    # Converted by ChatGPT:
    t = 2166136261
    for char in str:
        t ^= ord(char)
        t = (t * 16777619) & 0xFFFFFFFF    
    t ^= t >> 16
    t = (t * 2246822507) & 0xFFFFFFFF
    t ^= t >> 13
    t = (t * 3266489909) & 0xFFFFFFFF
    t ^= t >> 16
    return f"{t & 0xFFFFFFFF:08x}"


def get_config(user_agent=''):
    # getConfig() {
    #     return [screen?.width + screen?.height, "" + new Date, performance?.memory?.jsHeapSizeLimit, Math?.random(), navigator.userAgent, Bs(Array.from(document.scripts).map(t => t?.src).filter(t => t)), (Array.from(document.scripts || []).map(t => t?.src?.match("c/[^/]*/_")).filter(t => t?.length)[0] ?? [])[0] ?? document.documentElement.getAttribute("data-build"), navigator.language, navigator.languages?.join(","), Math?.random(), B6(), Bs(Object.keys(document)), Bs(Object.keys(window)), performance.now(), this.sid, [...new URLSearchParams(window.location.search).keys()].join(","), navigator?.hardwareConcurrency, performance.timeOrigin]
    # }
    global fp
    global document_keys
    global navigator_key_values

    if not fp:
        screen = Screen(min_width=1280, max_width=5120, min_height=720, max_height=2880)
        fingerprints = FingerprintGenerator(screen=screen)
        # if user_agent:
            # TODO: generate fingerprint from user_agent
            # header = HeaderGenerator().generate(user_agent=user_agent)    
        fp = fingerprints.generate(browser=("chrome", "firefox", "safari", "edge"), os=("windows", "macos", "android", "ios"), device=("desktop", "mobile"), locale=("en-US", "en", "en-GB"))
        navigator_key_values = ["vendorSub\xe2\x88\x92", "productSub\xe2\x88\x92" + str(fp.navigator.productSub), "vendor\xe2\x88\x92" + fp.navigator.vendor, "maxTouchPoints\xe2\x88\x92" + str(fp.navigator.maxTouchPoints), "scheduling\xe2\x88\x92[object Scheduling]", "userActivation\xe2\x88\x92[object UserActivation]", "doNotTrack", "geolocation\xe2\x88\x92[object Geolocation]", "connection\xe2\x88\x92[object NetworkInformation]", "plugins\xe2\x88\x92[object PluginArray]", "mimeTypes\xe2\x88\x92[object MimeTypeArray]", "pdfViewerEnabled\xe2\x88\x92" + str(fp.navigator.extraProperties['pdfViewerEnabled']).lower(), "webkitTemporaryStorage\xe2\x88\x92[object DeprecatedStorageQuota]", "webkitPersistentStorage\xe2\x88\x92[object DeprecatedStorageQuota]", "windowControlsOverlay\xe2\x88\x92[object WindowControlsOverlay]", "hardwareConcurrency\xe2\x88\x92" + str(fp.navigator.hardwareConcurrency), "cookieEnabled\xe2\x88\x92true", "appCodeName\xe2\x88\x92" + fp.navigator.appCodeName, "appName\xe2\x88\x92" + fp.navigator.appName, "appVersion\xe2\x88\x92" + fp.navigator.appVersion, "platform\xe2\x88\x92" + fp.navigator.platform, "product\xe2\x88\x92" + fp.navigator.product, "userAgent\xe2\x88\x92" + fp.navigator.userAgent, "language\xe2\x88\x92" + fp.navigator.language, "languages\xe2\x88\x92" + ','.join(fp.navigator.languages), "onLine\xe2\x88\x92true", "webdriver\xe2\x88\x92" + str(fp.navigator.webdriver).lower(), "getGamepads\xe2\x88\x92function getGamepads() { [native code] }", "javaEnabled\xe2\x88\x92function javaEnabled() { [native code] }", "sendBeacon\xe2\x88\x92function sendBeacon() { [native code] }", "vibrate\xe2\x88\x92function vibrate() { [native code] }", "deprecatedRunAdAuctionEnforcesKAnonymity\xe2\x88\x92false", "protectedAudience\xe2\x88\x92[object ProtectedAudience]", "bluetooth\xe2\x88\x92[object Bluetooth]", "storageBuckets\xe2\x88\x92[object StorageBucketManager]", "clipboard\xe2\x88\x92[object Clipboard]", "credentials\xe2\x88\x92[object CredentialsContainer]", "keyboard\xe2\x88\x92[object Keyboard]", "managed\xe2\x88\x92[object NavigatorManagedData]", "mediaDevices\xe2\x88\x92[object MediaDevices]", "storage\xe2\x88\x92[object StorageManager]", "serviceWorker\xe2\x88\x92[object ServiceWorkerContainer]", "virtualKeyboard\xe2\x88\x92[object VirtualKeyboard]", "wakeLock\xe2\x88\x92[object WakeLock]", "deviceMemory\xe2\x88\x92" + str(fp.navigator.deviceMemory), "userAgentData\xe2\x88\x92[object NavigatorUAData]", "login\xe2\x88\x92[object NavigatorLogin]", "ink\xe2\x88\x92[object Ink]", "mediaCapabilities\xe2\x88\x92[object MediaCapabilities]", "devicePosture\xe2\x88\x92[object DevicePosture]", "hid\xe2\x88\x92[object HID]", "locks\xe2\x88\x92[object LockManager]", "gpu\xe2\x88\x92[object GPU]", "mediaSession\xe2\x88\x92[object MediaSession]", "permissions\xe2\x88\x92[object Permissions]", "presentation\xe2\x88\x92[object Presentation]", "serial\xe2\x88\x92[object Serial]", "usb\xe2\x88\x92[object USB]", "xr\xe2\x88\x92[object XRSystem]", "adAuctionComponents\xe2\x88\x92function adAuctionComponents() { [native code] }", "runAdAuction\xe2\x88\x92function runAdAuction() { [native code] }", "canLoadAdAuctionFencedFrame\xe2\x88\x92function canLoadAdAuctionFencedFrame() { [native code] }", "canShare\xe2\x88\x92function canShare() { [native code] }", "share\xe2\x88\x92function share() { [native code] }", "clearAppBadge\xe2\x88\x92function clearAppBadge() { [native code] }", "getBattery\xe2\x88\x92function getBattery() { [native code] }", "getUserMedia\xe2\x88\x92function () { [native code] }", "requestMIDIAccess\xe2\x88\x92function requestMIDIAccess() { [native code] }", "requestMediaKeySystemAccess\xe2\x88\x92function requestMediaKeySystemAccess() { [native code] }", "setAppBadge\xe2\x88\x92function setAppBadge() { [native code] }", "webkitGetUserMedia\xe2\x88\x92function webkitGetUserMedia() { [native code] }", "clearOriginJoinedAdInterestGroups\xe2\x88\x92function clearOriginJoinedAdInterestGroups() { [native code] }", "createAuctionNonce\xe2\x88\x92function createAuctionNonce() { [native code] }", "joinAdInterestGroup\xe2\x88\x92function joinAdInterestGroup() { [native code] }", "leaveAdInterestGroup\xe2\x88\x92function leaveAdInterestGroup() { [native code] }", "updateAdInterestGroups\xe2\x88\x92function updateAdInterestGroups() { [native code] }", "deprecatedReplaceInURN\xe2\x88\x92function deprecatedReplaceInURN() { [native code] }", "deprecatedURNToURL\xe2\x88\x92function deprecatedURNToURL() { [native code] }", "getInstalledRelatedApps\xe2\x88\x92function getInstalledRelatedApps() { [native code] }", "getInterestGroupAdAuctionData\xe2\x88\x92function getInterestGroupAdAuctionData() { [native code] }", "registerProtocolHandler\xe2\x88\x92function registerProtocolHandler() { [native code] }", "unregisterProtocolHandler\xe2\x88\x92function unregisterProtocolHandler() { [native code] }"]

    if not document_keys:
        document_keys = ["location", "__reactContainer$" + utils.random_base36_string(), "_reactListening" + utils.random_base36_string()]

    # TODO: sizes?
    js_heap_size_limit = random.choice([2248146944, 4294705152])

    # TODO: ramdomize timezone
    date = get_datetime_now().strftime("%a %b %d %Y %H:%M:%S GMT%z") + ' (Eastern Daylight Time)'

    return [
        fp.screen.width + fp.screen.height,
        date,
        js_heap_size_limit,
        random.random(),
        fp.navigator.userAgent,
        None,
        data_build,
        fp.navigator.language,
        ','.join(fp.navigator.languages),
        random.random(),
        random.choice(navigator_key_values),
        random.choice(document_keys),
        random.choice(window_keys),
        performance_now(),
        str(uuid.uuid4()),
        "",
        fp.navigator.hardwareConcurrency,
        time_origin
    ]


def _generate_answer(seed, difficulty):
    r = 'e'
    n = len(difficulty)
    o = performance_now()
    for a in range(5e5):
        # sleep for 10 ms
        sleep(0.01)
        cfg = get_config()
        cfg[3] = 1
        cfg[9] = round(performance_now() - o)
        c = base64.b64encode(json.dumps(cfg, separators=(',', ':')).encode('utf-8')).decode('utf-8')
        if fnv_hash(seed + c)[0:n] <= difficulty:
            return c + '~S'

    # } catch (s) {
    #     r = Os(String(s))
    # } 
    return 'wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D' + r


# https://github.com/xtekky/gpt4free/blob/main/g4f/Provider/openai/new.py#L477
def process_turnstile_token(dx: str, p: str) -> str:
    result = []
    p_length = len(p)
    if p_length != 0:
        for i, r in enumerate(dx):
            result.append(chr(ord(r) ^ ord(p[i % p_length])))
    else:
        result = list(dx)
    return "".join(result)


def get_content(url, args, site_json, save_debug=False):
    global data_build
    global time_origin

    s = curl_cffi.Session(impersonate="chrome", proxies=config.proxies)
    r = s.get('https://chatgpt.com')
    if r.status_code != 200:
        return None

    time_origin = get_datetime_now().timestamp() * 1000

    m = re.search(r'data-build="([^"]+)', r.text)
    if m:
        data_build = m.group(1)
    else:
        data_build = 'prod-0ee440232733c2d20db755d56a16313a68930af9'

    m = re.search(r'"WebAnonymousCookieID\\",\\"([a-f0-9\-]+)', r.text)
    if m:
        device_id = m.group(1)
    else:
        device_id = str(uuid.uuid4())

    # m = re.search(r'"user_agent\\",\\"([a-f0-9\-]+)', r.text)
    # if m:
    #     user_agent = m.group(1)
    # else:
    #     user_agent = ''

    # n = performance.now()
    # r = this.getConfig()
    # return r[3] = 1,
    #     r[9] = Math.round(performance.now() - n),
    #     Os(r)
    n = performance_now()
    cfg = get_config()
    cfg[3] = 1
    cfg[9] = round(performance_now() - n)
    p = 'gAAAAAC' + base64.b64encode(json.dumps(cfg, separators=(',', ':')).encode('utf-8')).decode('utf-8')

    requirements_headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "oai-device-id": device_id,
        "oai-language": "en-US",
        "pragma": "no-cache",
        "priority": "u=1, i"
      }
    r = s.post('https://chatgpt.com/backend-anon/sentinel/chat-requirements', json={"p": p}, headers=requirements_headers)
    if r.status_code != 200:
        return None

    req_json = r.json()
    if save_debug:
        utils.write_file(req_json, './debug/requirements.json')

    conv_headers = {
        "accept": "text/event-stream",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "oai-device-id": device_id,
        "oai-echo-logs": "0,2757,0,1207612,1,1207635,0,11479176,0,11501316,3,11511309",
        "oai-language": "en-US",
        "openai-sentinel-chat-requirements-token": req_json['token'],
        "openai-sentinel-proof-token": "",
        "openai-sentinel-turnstile-token": "",
        "pragma": "no-cache",
        "priority": "u=1, i"
    }

    if req_json['proofofwork']['required']:
        conv_headers['openai-sentinel-proof-token'] = 'gAAAAAB' + _generate_answer(req_json['proofofwork']['seed'], req_json['proofofwork']['difficulty'])

    if req_json['turnstile']['required']:
        tokens = process_turnstile_token(base64.b64decode(req_json['turnstile']['dx']).decode(), p)


    return None


import base64
import json

# Instruction dispatcher and shared memory
registry = {}

# Human-readable opcode names
OPCODES = {
    "EXECUTOR": 0,
    "XOR_DECRYPT": 1,
    "SET_VALUE": 2,
    "RESOLVE": 3,
    "REJECT": 4,
    "APPEND_OR_CONCAT": 5,
    "GET_INDEX": 6,
    "BIND_METHOD": 24,
    "CALL_FUNC": 7,
    "COPY_VALUE": 8,
    "INSTR_QUEUE": 9,
    "STORE_GLOBAL": 10,
    "MATCH_SCRIPT_SRC": 11,
    "STORE_REGISTRY": 12,
    "TRY_CALL_FUNC": 13,
    "JSON_PARSE": 14,
    "JSON_STRINGIFY": 15,
    "XOR_KEY": 16,
    "CALL_AND_STORE": 17,
    "BASE64_DECODE": 18,
    "BASE64_ENCODE": 19,
    "IF_EQUALS_CALL": 20,
    "IF_ABS_DIFF_GT_CALL": 21,
    "NOOP1": 22,
    "IF_DEFINED_CALL": 23,
    "NOOP2": 25
}

# Simple XOR cipher
def xor_cipher(data, key):
    return ''.join(chr(ord(data[i]) ^ ord(key[i % len(key)])) for i in range(len(data)))

# Initializes the instruction handlers
def initialize_vm():
    registry.clear()

    # Core executor (reused by dispatcher)
    registry[OPCODES["EXECUTOR"]] = execute_program

    registry[OPCODES["XOR_DECRYPT"]] = lambda target, key: registry.__setitem__(target, xor_cipher(str(registry[target]), str(registry[key])))
    registry[OPCODES["SET_VALUE"]] = lambda target, value: registry.__setitem__(target, value)
    registry[OPCODES["APPEND_OR_CONCAT"]] = lambda target, source: registry.__setitem__(target, registry[target] + registry[source] if isinstance(registry[target], list) else str(registry[target]) + str(registry[source]))
    registry[OPCODES["GET_INDEX"]] = lambda target, arr, idx: registry.__setitem__(target, registry[arr][registry[idx]])
    registry[OPCODES["CALL_FUNC"]] = lambda func_key, *args: registry[func_key](*[registry[arg] for arg in args])
    registry[OPCODES["CALL_AND_STORE"]] = lambda target, func_key, *args: registry.__setitem__(target, registry[func_key](*[registry[arg] for arg in args]))
    registry[OPCODES["TRY_CALL_FUNC"]] = lambda err_key, func_key, *args: try_exec(err_key, func_key, *args)
    registry[OPCODES["COPY_VALUE"]] = lambda target, source: registry.__setitem__(target, registry[source])
    registry[OPCODES["JSON_PARSE"]] = lambda target, source: registry.__setitem__(target, json.loads(registry[source]))
    registry[OPCODES["JSON_STRINGIFY"]] = lambda target, source: registry.__setitem__(target, json.dumps(registry[source]))
    registry[OPCODES["BASE64_DECODE"]] = lambda key: registry.__setitem__(key, base64.b64decode(registry[key]).decode())
    registry[OPCODES["BASE64_ENCODE"]] = lambda key: registry.__setitem__(key, base64.b64encode(str(registry[key]).encode()).decode())
    registry[OPCODES["IF_EQUALS_CALL"]] = lambda a, b, func_key, *args: registry[func_key](*args) if registry[a] == registry[b] else None
    registry[OPCODES["IF_ABS_DIFF_GT_CALL"]] = lambda a, b, threshold, func_key, *args: registry[func_key](*args) if abs(registry[a] - registry[b]) > registry[threshold] else None
    registry[OPCODES["IF_DEFINED_CALL"]] = lambda key, func_key, *args: registry[func_key](*args) if key in registry else None
    registry[OPCODES["BIND_METHOD"]] = lambda target, obj_key, attr_key: registry.__setitem__(target, getattr(registry[obj_key], registry[attr_key]))
    registry[OPCODES["NOOP1"]] = lambda: None
    registry[OPCODES["NOOP2"]] = lambda: None
    registry[OPCODES["STORE_REGISTRY"]] = lambda key: registry.__setitem__(key, registry)
    registry[OPCODES["MATCH_SCRIPT_SRC"]] = lambda target, pattern_key: registry.__setitem__(target, None)  # stub for browser context
    registry[OPCODES["STORE_GLOBAL"]] = lambda key: registry.__setitem__(key, globals())  # simulate "window"

# Helper for exception-safe function calls
def try_exec(error_key, func_key, *args):
    try:
        registry[func_key](*args)
    except Exception as e:
        registry[error_key] = str(e)

# Sets the encryption key
def set_xor_key(key):
    initialize_vm()
    registry[OPCODES["XOR_KEY"]] = key

# Main execution function
def execute_program(encoded_payload):
    import threading

    def runner(resolve, reject):
        op_count = 0
        registry[OPCODES["RESOLVE"]] = lambda val: resolve(base64.b64encode(str(val).encode()).decode())
        registry[OPCODES["REJECT"]] = lambda val: reject(base64.b64encode(str(val).encode()).decode())

        try:
            decoded = base64.b64decode(encoded_payload).decode()
            decrypted = xor_cipher(decoded, str(registry[OPCODES["XOR_KEY"]]))
            instructions = json.loads(decrypted)
            registry[OPCODES["INSTR_QUEUE"]] = instructions

            while registry[OPCODES["INSTR_QUEUE"]]:
                inst = registry[OPCODES["INSTR_QUEUE"]].pop(0)
                print(inst)
                opcode, *args = inst
                registry[opcode](*args)
                op_count += 1

            resolve(base64.b64encode(str(op_count).encode()).decode())

        except Exception as e:
            resolve(base64.b64encode(f"{op_count}: {e}".encode()).decode())

    class Promise:
        def __init__(self, fn):
            self.result = None
            self.done = threading.Event()

            def resolve(value):
                self.result = value
                self.done.set()

            def reject(value):
                self.result = f"Error: {value}"
                self.done.set()

            threading.Thread(target=fn, args=(resolve, reject)).start()

        def wait(self):
            self.done.wait()
            return self.result

    return Promise(runner)
