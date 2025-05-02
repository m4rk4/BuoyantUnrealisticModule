import base64, html, json, math, pytz, random, re, requests, time
from browserforge.fingerprints import Screen, FingerprintGenerator
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlencode, urlsplit

import config, utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    page_html = get_url_html(url)
    if not page_html:
        return None
    if save_debug:
        utils.write_file(page_html, './debug/debug.html')

    page_soup = BeautifulSoup(page_html, 'lxml')
    el = page_soup.find('script', id='pageItemData')
    if not el:
        logger.warning('unable to find pageItemData in ' + url)
        return None

    page_data = json.loads(el.string)
    if save_debug:
        utils.write_file(page_data, './debug/debug.json')

    split_url = urlsplit(url)

    item = {}
    item['id'] = page_data['id']
    item['url'] = 'https://' + split_url.netloc + page_data['path']
    item['title'] = page_data['title']

    # TODO: difference between publicationTimestamp and originalPublicationTimestamp
    dt = datetime.fromisoformat(page_data['publicationTimestamp'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {
        "name": page_data['viewProperties']['analyticsModel']['authorName']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if page_data.get('associatedRichTerms'):
        item['tags'] = [x['title'] for x in page_data['associatedRichTerms']]

    if page_data.get('primaryImage'):
        item['image'] = 'https://{}/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_1200/{}/{}.{}'.format(split_url.netloc, page_data['primaryImage']['publicId'], page_data['primaryImage']['title'], page_data['primaryImage']['format'])

    if page_data.get('metaDescription'):
        item['summary'] = page_data['metaDescription']
    elif page_data.get('teaser'):
        item['summary'] = page_data['teaser']
    elif page_data.get('dek'):
        item['summary'] = page_data['dek']

    item['content_html'] = ''
    if page_data.get('dek'):
        item['content_html'] += '<p><em>' + page_data['dek'] + '</em></p>'

    body = page_soup.find(class_='m-detail--body')
    if body:
        el = page_soup.find(class_=['m-detail-header--media', 'm-detail--feature-container'])
        if el:
            body.insert(0, el)

        for el in body.find_all(['phoenix-super-link', 'script']):
            el.decompose()

        for el in body.find_all(class_=['m-in-content-ad-row', 'm-in-content-ad']):
            el.decompose()

        for el in body.find_all(id='action_button_container'):
            el.decompose()

        for el in body.find_all('a', attrs={"onclick": True}):
            del el['onclick']

        for el in body.select('p:has(> strong)'):
            if re.search(r'^(Next:|Related:|Sign up)', el.strong.get_text().strip(), flags=re.I):
                el.decompose()

        for el in body.find_all('div', recursive=False):
            new_html = ''
            if el.find('phoenix-picture'):
                it = el.find('img')
                if it:
                    paths = list(filter(None, urlsplit(it['data-src']).path[1:].split('/')))
                    img_src = 'https://{}/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_1200/{}/{}'.format(split_url.netloc, paths[-2], paths[-1])
                    captions = []
                    it = el.find(class_='tml-image--caption')
                    if it:
                        captions.append(it.decode_contents())
                    it = el.find(class_='tml-image--attribution')
                    if it:
                        captions.append(it.decode_contents())
                    new_html = utils.add_image(img_src, ' | '.join(captions))
            elif el.find('phx-gallery-image'):
                if '_gallery' in item:
                    logger.warning('multiple galleries in ' + item['url'])
                item['_gallery'] = []
                new_html += '<h3><a href="{}/gallery?url={}" target="_blank">View photo gallery</a></h3>'.format(config.server, quote_plus(item['url']))
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                for it in el.find_all('phx-gallery-image'):
                    img_src = it['data-full-src']
                    paths = list(filter(None, urlsplit(img_src).path[1:].split('/')))
                    thumb = 'https://{}/.image/c_limit%2Ccs_srgb%2Cfl_progressive%2Cq_auto:good%2Cw_640/{}/{}'.format(split_url.netloc, paths[-2], paths[-1])
                    if it.get('data-caption-html'):
                        caption = BeautifulSoup(html.unescape(it['data-caption-html']), 'html.parser').get_text()
                    else:
                        caption = ''
                    new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
                    item['_gallery'].append({"src": img_src, "caption": caption, "thumb": thumb})
                new_html += '</div>'
            elif el.find('phoenix-video'):
                it = el.find('phoenix-video')
                new_html += utils.add_embed('https://cdn.jwplayer.com/v2/media/' + it['video-id'])
            # elif el.find('phoenix-exco-player'):
            #     player_url = 'https://player.ex.co/player/' + player_id
            #     player = utils.get_url_html(player_url)
            #     if not player:
            #         return None
            #     m = re.search(r'window\.STREAM_CONFIGS\[\'{}\'\] = (.*?);\n'.format(player_id), player)
            #     if not m:
            #         logger.warning('unable to find STREAM_CONFIGS in ' + player_url)
            #         return None
            #     stream_config = json.loads(m.group(1))
            #     utils.write_file(stream_config, './debug/video.json')
            #     new_html = utils.add_video(stream_config['contents'][0]['video']['mp4']['src'], 'video/mp4', stream_config['contents'][0]['poster'], stream_config['contents'][0]['title'])
            elif el.find('phoenix-twitter-embed'):
                new_html = utils.add_embed(el.find('phoenix-twitter-embed')['tweet-url'])
            elif el.find('phoenix-instagram-embed'):
                new_html = utils.add_embed(el.find('phoenix-instagram-embed')['src'])
            elif el.find('phoenix-tiktok-embed'):
                new_html = utils.add_embed(el.find('phoenix-tiktok-embed')['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled body item in ' + item['url'])
                print(str(el))

        item['content_html'] += body.decode_contents()
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)


def simmouse_movements(num_events=100):
    events = []
    for _ in range(num_events):
        event = {
            "clientX": random.randint(0, 1000),
            "clientY": random.randint(0, 1000),
            "movementX": random.randint(-50, 50),
            "movementY": random.randint(-50, 50),
            "screenX": random.randint(0, 1000),
            "screenY": random.randint(0, 1000),
            "timeStamp": random.uniform(0, 5000)
        }
        events.append(event)
    return events


def calculate_mm_md(events):
    max_distance = 0
    prev_event = None
    for event in events:
        if prev_event:
            dx = event["clientX"] - prev_event["clientX"]
            dy = event["clientY"] - prev_event["clientY"]
            distance = math.sqrt(dx**2 + dy**2)
            if distance > max_distance:
                max_distance = distance
        prev_event = event
    return max_distance


def calculate_es_sigmdn(events):
    x = sum(math.log(e["timeStamp"]) for e in events)
    q = len(events)
    y = sum(math.log(e["timeStamp"])**2 for e in events)
    return math.sqrt((q * y - x * x) / (q * (q - 1))) / 1000


def calculate_es_mumdn(events):
    timestamps = [e["timeStamp"] for e in events]
    q = len(events)
    return (sum(timestamps) / q) / 1000


def calculate_es_distmdn(events):
    distances = []
    prev_event = None
    for event in events:
        if prev_event:
            dx = event["clientX"] - prev_event["clientX"]
            dy = event["clientY"] - prev_event["clientY"]
            distances.append(math.sqrt(dx**2 + dy**2))
        prev_event = event
    distances.sort()
    mid = len(distances) // 2
    return distances[mid]


def calculate_es_angsmdn(events):
    start_angles = [random.uniform(-math.pi, math.pi) for _ in events]
    start_angles.sort()
    mid = len(start_angles) // 2
    return start_angles[mid]


def calculate_es_angemdn(events):
    end_angles = [random.uniform(-math.pi, math.pi) for _ in events]
    end_angles.sort()
    mid = len(end_angles) // 2
    return end_angles[mid]


def calculate_event_variables(event_counters):
    m_s_c = event_counters["scroll"]
    m_m_c = event_counters["mousemove"]
    m_c_c = event_counters["click"]
    m_cm_r = m_c_c / m_m_c if m_m_c != 0 else 0
    m_ms_r = m_m_c / m_s_c if m_s_c != 0 else 0
    return {
        "m_s_c": m_s_c,
        "m_m_c": m_m_c,
        "m_c_c": m_c_c,
        "m_cm_r": m_cm_r,
        "m_ms_r": m_ms_r
    }


def generate_mouse_movements():
    mouse_events = simmouse_movements()
    mm_md = calculate_mm_md(mouse_events)
    es_sigmdn = calculate_es_sigmdn(mouse_events)
    es_mumdn = calculate_es_mumdn(mouse_events)
    es_distmdn = calculate_es_distmdn(mouse_events)
    es_angsmdn = calculate_es_angsmdn(mouse_events)
    es_angemdn = calculate_es_angemdn(mouse_events)
    # Change depending on device/use touch if automating on mobile user agent
    event_counters = {
        "mousemove": len(mouse_events),
        "click": random.randint(0, 10),
        "scroll": random.randint(0, 600),
        "touchstart": 0,
        "touchend": 0,
        "touchmove": 0,
        "keydown": 0,
        "keyup": 0
    }
    event_vars = calculate_event_variables(event_counters)
    return {
        "mp_cx": random.choice(mouse_events)["clientX"],
        "mp_cy": random.choice(mouse_events)["clientY"],
        "mm_md": mm_md,
        "es_sigmdn": es_sigmdn,
        "es_mumdn": es_mumdn,
        "es_distmdn": es_distmdn,
        "es_angsmdn": es_angsmdn,
        "es_angemdn": es_angemdn,
        **event_vars
    }


def get_url_html(url, ddk='2AC20A4365547ED96AE26618B66966', ddv='4.38.0'):
    # https://github.com/Millionarc/datadome-cookie-generator
    # https://github.com/ellisfan/bypass-datadome
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

    split_url = urlsplit(url)

    s = requests.Session()
    r = s.get(url, headers=fp.headers, allow_redirects=False)
    if r.status_code == 200:
        return r.text

    cookies = s.cookies.get_dict()
    if not cookies.get('datadome'):
        logger.warning('invalid session, no datadome cookie')
        return ''

    dd_cookie = cookies['datadome']

    # headers = fp.headers.copy()
    # headers['cookie'] = 'datadome=' + dd_cookie
    # r = s.get(r.url, headers=headers)
    # if r.status_code == 200:
    #     return r.text

    # page_soup = BeautifulSoup(r.text, 'lxml')
    # el = page_soup.find('script', string=re.compile(r'var dd='))
    # if not el:
    #     return None
    # i = el.string.find('{')
    # j = el.string.rfind('}') + 1
    # dd_json = json.loads(el.string[i:j].replace('\'', '"'))
    # dd_cookie = dd_json['cookie']
    # ddk = dd_json['hsh']

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded",
        "origin": url,
        "priority": "u=1, i",
        "sec-ch-ua": fp.headers.get('sec-ch-ua'),
        "sec-ch-ua-mobile": fp.headers.get('sec-ch-ua-mobile'),
        "sec-ch-ua-platform": fp.headers.get('sec-ch-ua-platform'),
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": fp.headers.get('User-Agent')
    }

    # ttst = related to performance.now() - range?
    # tagpu = ?? - range?
    # br_h = window.innerHeight
    # br_w = window.innerWidth
    # tzp = timezone
    # tz = timezone offset (negative)
    tzp = 'America/New_York'
    m = re.search(r'(\+|\-)(\d\d)(\d\d)', datetime.now(pytz.timezone(tzp)).strftime('%z'))
    tz = 60 * int(m.group(2)) + int(m.group(3))
    if m.group(1) == '+':
        tz = -tz

    # https://github.com/post04/datadome-documentation
    js_data = {
        "ttst": float(f"{random.randint(5, 30)}.{random.randint(100000000000000, 999999999999999)}"),
        "ifov": False,
        "hc": fp.navigator.hardwareConcurrency,
        "br_oh": fp.screen.availHeight,
        "br_ow": fp.screen.availWidth,
        "ua": fp.headers.get("User-Agent"),
        "wbd": False,
        "dp0": True,
        "tagpu": float(f"{random.randint(0, 2)}.{random.randint(1000000000000, 9999999999999)}"),
        "wdif": False,
        "wdifrm": False,
        "npmtm": False,
        "br_h": fp.screen.availHeight - 108,
        "br_w": fp.screen.availWidth - 55, 
        "isf": False,
        "nddc": 1,
        "rs_h": fp.screen.height,
        "rs_w": fp.screen.width,
        "rs_cd": fp.screen.pixelDepth,
        "phe": False,
        "nm": False,
        "jsf": False,
        "lg": fp.navigator.language,
        "pr": 1,
        "ars_h": fp.screen.availHeight,
        "ars_w": fp.screen.availWidth,
        "tz": tz,
        "str_ss": True,
        "str_ls": True,
        "str_idb": True,
        "str_odb": False,
        "plgod": False,
        "plg": 5,
        "plgne": True,
        "plgre": True,
        "plgof": False,
        "plggt": False,
        "pltod": False,
        "hcovdr": False,
        "hcovdr2": False,
        "plovdr": False,
        "plovdr2": False,
        "ftsovdr": False,
        "ftsovdr2": False,
        "lb": False,
        "eva": 33,
        "lo": True,
        "ts_mtp": fp.navigator.maxTouchPoints,
        "ts_tec": False,
        "ts_tsa": False,
        "vnd": fp.navigator.vendor or "NA",
        "bid": "NA",
        "mmt": "application/pdf,text/pdf",
        "plu": "PDF Viewer,Chrome PDF Viewer,Chromium PDF Viewer,Microsoft Edge PDF Viewer,WebKit built-in PDF",
        "hdn": False,
        "awe": False,
        "geb": False,
        "dat": False,
        "med": "defined",
        "aco": "probably",
        "acots": False,
        "acmp": "probably",
        "acmpts": True,
        "acw": "probably",
        "acwts": False,
        "acma": "maybe",
        "acmats": False,
        "acaa": "probably",
        "acaats": True,
        "ac3": "maybe",
        "ac3ts": False,
        "acf": "probably",
        "acfts": False,
        "acmp4": "maybe",
        "acmp4ts": False,
        "acmp3": "probably",
        "acmp3ts": False,
        "acwm": "maybe",
        "acwmts": False,
        "ocpt": False,
        "vco": "",
        "vcots": False,
        "vch": "probably",
        "vchts": True,
        "vcw": "probably",
        "vcwts": True,
        "vc3": "maybe",
        "vc3ts": False,
        "vcmp": "",
        "vcmpts": False,
        "vcq": "",
        "vcqts": False,
        "vc1": "probably",
        "vc1ts": True,
        "dvm": fp.navigator.deviceMemory,
        "sqt": False,
        "so": "landscape-primary",
        "wdw": True,
        "cokys": base64.b64encode('loadTimescsiapp'.encode('utf-8')).decode('utf-8') + 'L=',
        "ecpc": False,
        "lgs": True,
        "lgsod": False,
        "psn": True,
        "edp": True,
        "addt": True,
        "wsdc": True,
        "ccsr": True,
        "nuad": True,
        "bcda": False,
        "idn": True,
        "capi": False,
        "svde": False,
        "vpbq": True,
        "ucdv": False,
        "spwn": False,
        "emt": False,
        "bfr": False,
        "dbov": False,
        "cfpfe": "ZnVuY3Rpb24gYShlKXt0cnl7Y29uc3QgdD1lLnF1ZXJ5U2VsZWN0b3IoImxpbmtbcmVsPSdjYW5vbmljYWwnXSIpO2lmKG51bGwhPT10KXJldHVybiB0LmhyZWZ9Y2F0Y2goZSl7fXJldHVybiBudWxsfQ==",
        "stcfp": base64.b64encode('ps://js.datadome.co/tags.js:2:88027)\n    at t.<computed>.dd_ad (https://js.datadome.co/tags.js:2:107026)\n    at https://js.datadome.co/tags.js:2:63761'.encode('utf-8')).decode('utf-8'),
        "ckwa": True,
        "prm": True,
        "cvs": True,
        "usb": "defined",
        "emd": "k:ai,vi,ao",
        "glvd": fp.videoCard.vendor or "NA",
        "glrd": fp.videoCard.renderer or "NA",
        "wwl": False,
        "jset": int(datetime.timestamp(datetime.now()))
    }

    data = {
        "jsDate": json.dumps(js_data, separators=(',', ':')),
        "eventCounters": [],
        "jsType": "ch",
        "cid": dd_cookie,
        "ddk": ddk,
        "Referer": quote_plus('https://' + split_url.netloc + '/'),
        "request": "%2F",
        "responsePage": "origin",
        "ddv": ddv
    }

    r_ddjs = requests.post('https://api-js.datadome.co/js/', headers=headers, data=urlencode(data))
    if r_ddjs.status_code != 200:
        return ''

    m = re.search(r'datadome=([^;]+)', r_ddjs.json()['cookie'])
    dd_cookie = m.group(1)
    print('datadome=' + dd_cookie)

    random_data = generate_mouse_movements()

    js_data.update({
        "tzp": tzp,
        "m_fmi": False,
        "mp_cx": random_data["mp_cx"],
        "mp_cy": random_data["mp_cy"],
        "mp_tr": random_data.get("mp_tr", True),
        "mp_mx": random_data.get("mp_mx", 0),
        "mp_my": random_data.get("mp_my", 0),
        "mp_sx": random_data.get("mp_sx", 0),
        "mp_sy": random_data.get("mp_sy", 0),
        "mm_md": random_data["mm_md"],
        "dcok": '.' + re.sub(r'^(www.)', '', split_url.netloc),
        "es_sigmdn": random_data["es_sigmdn"],
        "es_mumdn": random_data["es_mumdn"],
        "es_distmdn": random_data["es_distmdn"],
        "es_angsmdn": random_data["es_angsmdn"],
        "es_angemdn": random_data["es_angemdn"],
        "k_hA": None,
        "k_hSD": None,
        "k_pA": None,
        "k_pSD": None,
        "k_rA": None,
        "k_rSD": None,
        "k_ikA": None,
        "k_ikSD": None,
        "k_kdc": 0,
        "k_kuc": 0,
        "m_s_c": random_data["m_s_c"],
        "m_m_c": random_data["m_m_c"],
        "m_c_c": random_data["m_c_c"],
        "m_cm_r": random_data["m_cm_r"],
        "m_ms_r": random_data["m_ms_r"]
    })

        # "click": random_data["m_c_c"],
        # "scroll": random_data["m_s_c"],
    event_counters = {
        "mousemove": random_data["m_m_c"],
        "click": 0,
        "scroll": 0,
        "touchstart": 0,
        "touchend": 0,
        "touchmove": 0,
        "keydown": 0,
        "keyup": 0
    }

    data = {
        "jsDate": json.dumps(js_data, separators=(',', ':')),
        "eventCounters": json.dumps(event_counters, separators=(',', ':')),
        "jsType": "le",
        "cid": dd_cookie,
        "ddk": ddk,
        "Referer": quote_plus('https://' + split_url.netloc + '/'),
        "request": "%2F",
        "responsePage": "origin",
        "ddv": ddv
    }

    r_ddjs = requests.post('https://api-js.datadome.co/js/', headers=headers, data=urlencode(data))
    if r_ddjs.status_code != 200:
        return ''

    m = re.search(r'datadome=([^;]+)', r_ddjs.json()['cookie'])
    dd_cookie = m.group(1)
    print('datadome=' + dd_cookie)
    headers = fp.headers.copy()
    headers['cookie'] = 'ArenaGeo=eyJjb3VudHJ5Q29kZSI6IlVTIiwicmVnaW9uQ29kZSI6Ik9IIiwiaW5FRUEiOmZhbHNlfQ==;datadome=' + dd_cookie
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(r.status_code)
        return ''
    return r.text
