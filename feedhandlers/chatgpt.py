import base64, curl_cffi, json, pytz, random, re, uuid, STPyV8
from browserforge.fingerprints import Screen, FingerprintGenerator
from datetime import datetime, timedelta, timezone

import config, utils

import logging

logger = logging.getLogger(__name__)

# TODO: python version
def random_base36_string():
    with STPyV8.JSContext() as ctxt:
        return ctxt.eval('''Math.random().toString(36).slice(2);''')


def get_content(url, args, site_json, save_debug=False):
    s = curl_cffi.Session(impersonate="chrome", proxies=config.proxies)
    r = s.get('https://chatgpt.com')
    if r.status_code != 200:
        return None

    m = re.search(r'data-build="([^"]+)', r.text)
    if m:
        data_build = m.group(1)
    else:
        data_build = 'prod-0ee440232733c2d20db755d56a16313a68930af9'

    m = re.search(r'"WebAnonymousCookieID\\",\\"([a-f0-9\-]+)', r.text)
    if m:
        device_id = m.group(1)
    else:
        device_id = uuid.uuid4()

    screen = Screen(
        min_width=1280,
        max_width=5120,
        min_height=720,
        max_height=2880,
      )
    fingerprints = FingerprintGenerator(screen=screen)
    fp = fingerprints.generate(
        browser=("chrome", "firefox", "safari", "edge"),
        os=("windows", "macos"),
        device="desktop",
        locale=("en-US", "en"),
        http_version=2,
        strict=True,
        mock_webrtc=True
    )
    m = re.search(r'"user_agent\\",\\"([a-f0-9\-]+)', r.text)
    if m:
        user_agent = m.group(1)
    else:
        user_agent = fp.navigator.userAgent

    # TODO: ramdomize timezone
    dt = datetime.now(timezone.utc).astimezone(pytz.timezone('US/Eastern'))
    performance_time_origin = (dt.timestamp() * 10000) / 10
    performance_now = random.random() * 10000
    dt += timedelta(seconds=performance_time_origin/1000)
    date = dt.strftime("%a %b %d %Y %H:%M:%S GMT%z") + ' (Eastern Daylight Time)'

    # TODO: sizes?
    js_heap_size_limit = random.choice([2248146944, 4294705152])

    # getConfig() {
    #     return [screen?.width + screen?.height, "" + new Date, performance?.memory?.jsHeapSizeLimit, Math?.random(), navigator.userAgent, Bs(Array.from(document.scripts).map(t => t?.src).filter(t => t)), (Array.from(document.scripts || []).map(t => t?.src?.match("c/[^/]*/_")).filter(t => t?.length)[0] ?? [])[0] ?? document.documentElement.getAttribute("data-build"), navigator.language, navigator.languages?.join(","), Math?.random(), B6(), Bs(Object.keys(document)), Bs(Object.keys(window)), performance.now(), this.sid, [...new URLSearchParams(window.location.search).keys()].join(","), navigator?.hardwareConcurrency, performance.timeOrigin]
    # }
    # n = performance.now()
    # r = this.getConfig()
    # return r[3] = 1,
    #     r[9] = Math.round(performance.now() - n),
    #     Os(r)

    print('here!!!')
    document_keys = ["location", "__reactContainer$" + random_base36_string(), "_reactListening" + random_base36_string()]
    print(document_keys)

    window_keys = [0, "window", "self", "document", "name", "location", "customElements", "history", "navigation", "locationbar", "menubar", "personalbar", "scrollbars", "statusbar", "toolbar", "status", "closed", "frames", "length", "top", "opener", "parent", "frameElement", "navigator", "origin", "external", "screen", "innerWidth", "innerHeight", "scrollX", "pageXOffset", "scrollY", "pageYOffset", "visualViewport", "screenX", "screenY", "outerWidth", "outerHeight", "devicePixelRatio", "event", "clientInformation", "screenLeft", "screenTop", "styleMedia", "onsearch", "trustedTypes", "performance", "onappinstalled", "onbeforeinstallprompt", "crypto", "indexedDB", "sessionStorage", "localStorage", "onbeforexrselect", "onabort", "onbeforeinput", "onbeforematch", "onbeforetoggle", "onblur", "oncancel", "oncanplay", "oncanplaythrough", "onchange", "onclick", "onclose", "oncontentvisibilityautostatechange", "oncontextlost", "oncontextmenu", "oncontextrestored", "oncuechange", "ondblclick", "ondrag", "ondragend", "ondragenter", "ondragleave", "ondragover", "ondragstart", "ondrop", "ondurationchange", "onemptied", "onended", "onerror", "onfocus", "onformdata", "oninput", "oninvalid", "onkeydown", "onkeypress", "onkeyup", "onload", "onloadeddata", "onloadedmetadata", "onloadstart", "onmousedown", "onmouseenter", "onmouseleave", "onmousemove", "onmouseout", "onmouseover", "onmouseup", "onmousewheel", "onpause", "onplay", "onplaying", "onprogress", "onratechange", "onreset", "onresize", "onscroll", "onsecuritypolicyviolation", "onseeked", "onseeking", "onselect", "onslotchange", "onstalled", "onsubmit", "onsuspend", "ontimeupdate", "ontoggle", "onvolumechange", "onwaiting", "onwebkitanimationend", "onwebkitanimationiteration", "onwebkitanimationstart", "onwebkittransitionend", "onwheel", "onauxclick", "ongotpointercapture", "onlostpointercapture", "onpointerdown", "onpointermove", "onpointerrawupdate", "onpointerup", "onpointercancel", "onpointerover", "onpointerout", "onpointerenter", "onpointerleave", "onselectstart", "onselectionchange", "onanimationend", "onanimationiteration", "onanimationstart", "ontransitionrun", "ontransitionstart", "ontransitionend", "ontransitioncancel", "onafterprint", "onbeforeprint", "onbeforeunload", "onhashchange", "onlanguagechange", "onmessage", "onmessageerror", "onoffline", "ononline", "onpagehide", "onpageshow", "onpopstate", "onrejectionhandled", "onstorage", "onunhandledrejection", "onunload", "isSecureContext", "crossOriginIsolated", "scheduler", "alert", "atob", "blur", "btoa", "cancelAnimationFrame", "cancelIdleCallback", "captureEvents", "clearInterval", "clearTimeout", "close", "confirm", "createImageBitmap", "fetch", "find", "focus", "getComputedStyle", "getSelection", "matchMedia", "moveBy", "moveTo", "open", "postMessage", "print", "prompt", "queueMicrotask", "releaseEvents", "reportError", "requestAnimationFrame", "requestIdleCallback", "resizeBy", "resizeTo", "scroll", "scrollBy", "scrollTo", "setInterval", "setTimeout", "stop", "structuredClone", "webkitCancelAnimationFrame", "webkitRequestAnimationFrame", "chrome", "caches", "cookieStore", "ondevicemotion", "ondeviceorientation", "ondeviceorientationabsolute", "launchQueue", "sharedStorage", "documentPictureInPicture", "fetchLater", "getDigitalGoodsService", "getScreenDetails", "queryLocalFonts", "showDirectoryPicker", "showOpenFilePicker", "showSaveFilePicker", "originAgentCluster", "onpageswap", "onpagereveal", "credentialless", "fence", "speechSynthesis", "oncommand", "onscrollend", "onscrollsnapchange", "onscrollsnapchanging", "webkitRequestFileSystem", "webkitResolveLocalFileSystemURL", "__oai_SSR_HTML", "__reactRouterContext", "$RC", "__oai_SSR_TTI", "__reactRouterManifest", "__reactRouterVersion", "DD_RUM", "__REACT_INTL_CONTEXT__", "__STATSIG__", "regeneratorRuntime", "DD_LOGS", "__mobxInstanceCount", "__mobxGlobals", "_g", "__reactRouterRouteModules", "__reactRouterDataRouter", "__SEGMENT_INSPECTOR__", "MotionIsMounted", "_oaiHandleSessionExpired"]

    # TODO: sync these values with fp
    navigator_key_values = ["vendorSub\xe2\x88\x92","productSub\xe2\x88\x9220030107","vendor\xe2\x88\x92Google Inc.","maxTouchPoints\xe2\x88\x9210","scheduling\xe2\x88\x92[object Scheduling]","userActivation\xe2\x88\x92[object UserActivation]","doNotTrack","geolocation\xe2\x88\x92[object Geolocation]","connection\xe2\x88\x92[object NetworkInformation]","plugins\xe2\x88\x92[object PluginArray]","mimeTypes\xe2\x88\x92[object MimeTypeArray]","pdfViewerEnabled\xe2\x88\x92true","webkitTemporaryStorage\xe2\x88\x92[object DeprecatedStorageQuota]","webkitPersistentStorage\xe2\x88\x92[object DeprecatedStorageQuota]","windowControlsOverlay\xe2\x88\x92[object WindowControlsOverlay]","hardwareConcurrency\xe2\x88\x928","cookieEnabled\xe2\x88\x92true","appCodeName\xe2\x88\x92Mozilla","appName\xe2\x88\x92Netscape","appVersion\xe2\x88\x925.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0","platform\xe2\x88\x92Win32","product\xe2\x88\x92Gecko","userAgent\xe2\x88\x92Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0","language\xe2\x88\x92en-US","languages\xe2\x88\x92en-US,en,en-GB","onLine\xe2\x88\x92true","webdriver\xe2\x88\x92false","getGamepads\xe2\x88\x92function getGamepads() { [native code] }","javaEnabled\xe2\x88\x92function javaEnabled() { [native code] }","sendBeacon\xe2\x88\x92function sendBeacon() { [native code] }","vibrate\xe2\x88\x92function vibrate() { [native code] }","deprecatedRunAdAuctionEnforcesKAnonymity\xe2\x88\x92false","protectedAudience\xe2\x88\x92[object ProtectedAudience]","bluetooth\xe2\x88\x92[object Bluetooth]","storageBuckets\xe2\x88\x92[object StorageBucketManager]","clipboard\xe2\x88\x92[object Clipboard]","credentials\xe2\x88\x92[object CredentialsContainer]","keyboard\xe2\x88\x92[object Keyboard]","managed\xe2\x88\x92[object NavigatorManagedData]","mediaDevices\xe2\x88\x92[object MediaDevices]","storage\xe2\x88\x92[object StorageManager]","serviceWorker\xe2\x88\x92[object ServiceWorkerContainer]","virtualKeyboard\xe2\x88\x92[object VirtualKeyboard]","wakeLock\xe2\x88\x92[object WakeLock]","deviceMemory\xe2\x88\x928","userAgentData\xe2\x88\x92[object NavigatorUAData]","login\xe2\x88\x92[object NavigatorLogin]","ink\xe2\x88\x92[object Ink]","mediaCapabilities\xe2\x88\x92[object MediaCapabilities]","devicePosture\xe2\x88\x92[object DevicePosture]","hid\xe2\x88\x92[object HID]","locks\xe2\x88\x92[object LockManager]","gpu\xe2\x88\x92[object GPU]","mediaSession\xe2\x88\x92[object MediaSession]","permissions\xe2\x88\x92[object Permissions]","presentation\xe2\x88\x92[object Presentation]","serial\xe2\x88\x92[object Serial]","usb\xe2\x88\x92[object USB]","xr\xe2\x88\x92[object XRSystem]","adAuctionComponents\xe2\x88\x92function adAuctionComponents() { [native code] }","runAdAuction\xe2\x88\x92function runAdAuction() { [native code] }","canLoadAdAuctionFencedFrame\xe2\x88\x92function canLoadAdAuctionFencedFrame() { [native code] }","canShare\xe2\x88\x92function canShare() { [native code] }","share\xe2\x88\x92function share() { [native code] }","clearAppBadge\xe2\x88\x92function clearAppBadge() { [native code] }","getBattery\xe2\x88\x92function getBattery() { [native code] }","getUserMedia\xe2\x88\x92function () { [native code] }","requestMIDIAccess\xe2\x88\x92function requestMIDIAccess() { [native code] }","requestMediaKeySystemAccess\xe2\x88\x92function requestMediaKeySystemAccess() { [native code] }","setAppBadge\xe2\x88\x92function setAppBadge() { [native code] }","webkitGetUserMedia\xe2\x88\x92function webkitGetUserMedia() { [native code] }","clearOriginJoinedAdInterestGroups\xe2\x88\x92function clearOriginJoinedAdInterestGroups() { [native code] }","createAuctionNonce\xe2\x88\x92function createAuctionNonce() { [native code] }","joinAdInterestGroup\xe2\x88\x92function joinAdInterestGroup() { [native code] }","leaveAdInterestGroup\xe2\x88\x92function leaveAdInterestGroup() { [native code] }","updateAdInterestGroups\xe2\x88\x92function updateAdInterestGroups() { [native code] }","deprecatedReplaceInURN\xe2\x88\x92function deprecatedReplaceInURN() { [native code] }","deprecatedURNToURL\xe2\x88\x92function deprecatedURNToURL() { [native code] }","getInstalledRelatedApps\xe2\x88\x92function getInstalledRelatedApps() { [native code] }","getInterestGroupAdAuctionData\xe2\x88\x92function getInterestGroupAdAuctionData() { [native code] }","registerProtocolHandler\xe2\x88\x92function registerProtocolHandler() { [native code] }","unregisterProtocolHandler\xe2\x88\x92function unregisterProtocolHandler() { [native code] }"]
    
    get_config = [
        fp.screen.width + fp.screen.height,
        date,
        js_heap_size_limit,
        1,
        user_agent,
        None,
        data_build,
        fp.navigator.language,
        ','.join(fp.navigator.languages),
        1,
        random.choice(navigator_key_values),
        random.choice(document_keys),
        random.choice(window_keys),
        performance_now,
        uuid.uuid4(),
        "",
        fp.navigator.hardwareConcurrency,
        performance_time_origin
    ]

    requirements_token = 'gAAAAAC' + base64.b64encode(json.dumps(get_config, separators=(',', ':')))

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "oai-device-id": device_id,
        "oai-language": "en-US",
        "pragma": "no-cache",
        "priority": "u=1, i"
      }
    r = s.post('https://chatgpt.com/backend-anon/sentinel/chat-requirements', json={"p": requirements_token}, headers=headers)
    if r.status_code != 200:
        return None

    requirements_json = r.json()
    if save_debug:
        utils.write_file(requirements_json, './debug/requirements.json')

    return None