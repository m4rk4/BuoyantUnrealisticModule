import asyncio, curl_cffi, base64, glob, importlib, io, json, os, random, re, string, sys
import subprocess, time
# import certifi, primp
import requests
from bs4 import BeautifulSoup
import logging, logging.handlers
from flask import Flask, jsonify, make_response, render_template, redirect, Response, request, send_file, stream_with_context
from flask_cors import CORS
from io import BytesIO
from playwright.async_api import Playwright, async_playwright
from staticmap import StaticMap, CircleMarker
from urllib.parse import quote, quote_plus, urlsplit

import config, image_utils, utils
from feedhandlers import google, spotify

app = Flask(__name__)
CORS(app)


# Setup logger
LOG_FILENAME = './debug/debug.log'
handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=100 * 1024, backupCount=3)
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    datefmt='%Y-%m-%dT%H:%M:%S',
    handlers=[handler, logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

# Turn off debuging in some modules
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('chardet').setLevel(logging.WARNING)
logging.getLogger('filelock').setLevel(logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('pytube').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('requests_oauthlib').setLevel(logging.WARNING)
logging.getLogger('oauthlib').setLevel(logging.WARNING)
logging.getLogger('duckduckgo_search').setLevel(logging.WARNING)
logging.getLogger('rquest').setLevel(logging.WARNING)
logging.getLogger('primp').setLevel(logging.WARNING)
#logging.getLogger('flask_cors').setLevel(logging.DEBUG)


@app.template_filter()
def make_thumbnail(img_src):
    return '/image?url={}&height=100&crop=120,100'.format(quote(img_src))


@app.route('/feed', methods=['GET'])
def feed():
    args = request.args
    if 'debug' in args:
        save_debug = True
    else:
        save_debug = False

    if args.get('feedhandler'):
        handler = args['feedhandler']
    elif args.get('feedtype'):
        handler = args['feedtype']
    else:
        handler = ''

    url = args.get('url')

    module, site_json = utils.get_module(url, handler)
    if not module:
        return 'feed handler not found'

    args_copy = args.copy()
    if site_json.get('args'):
        args_copy.update(site_json['args'])

    feed = module.get_feed(url, args_copy, site_json, save_debug)
    if not feed:
        return 'No feed found'

    feed['feed_url'] = request.url

    if 'read' in args:
        return render_template('feed.html', title=feed['title'], link=feed['home_page_url'], items=feed['items'])
    return jsonify(feed)


@app.route('/test_handler', methods=['GET'])
def test_handler():
    args = request.args
    if 'feedhandler' not in args:
        return 'feed handler not specified'
    module_name = args['feedhandler']
    try:
      module = importlib.import_module('.{}'.format(module_name), 'feedhandlers')
    except:
      return 'unable to load module ' + args['feedhandler']

    sio = io.StringIO('')
    stream = logging.StreamHandler(sio)
    stream.setLevel(logging.DEBUG)
    logger.addHandler(stream)
    try:
        module.test_handler()
    except:
        pass
    logger.removeHandler(stream)
    stream.close()
    return sio.getvalue()


@app.route('/content', methods=['GET'])
def content():
    args = request.args
    if 'debug' in args:
        save_debug = True
    else:
        save_debug = False

    if args.get('feedhandler'):
        handler = args['feedhandler']
    elif args.get('feedtype'):
        handler = args['feedtype']
    else:
        handler = ''

    url = args.get('url')

    module, site_json = utils.get_module(url, handler)
    if not module:
        return 'content handler not found'

    args_copy = args.copy()
    if site_json.get('args'):
        args_copy.update(site_json['args'])


    content = module.get_content(url, args_copy, site_json, save_debug)

    if 'ai_summary' in args:
        if args['ai_summary'] in ['cloudflare', 'hf_summarizer', 'decopy_ai']:
            provider = args['ai_summary']
        else:
            provider = 'cloudflare'
        content['_ai_summary'] = utils.get_ai_summary(content['content_html'], False, provider, args)
        content['content_html'] += '<hr style="margin:2em 0;"><h2>AI Summary:</h2>' + content['_ai_summary']

    if 'read' in args:
        return render_template('content.html', content=content)

    return jsonify(content)


@app.route('/test', methods=['GET'])
def test():
    args = request.args
    if 'debug' in args:
        save_debug = True
    else:
        save_debug = False

    if args.get('feedhandler'):
        handler = args['feedhandler']
    elif args.get('feedtype'):
        handler = args['feedtype']
    else:
        handler = ''

    url = args.get('url')

    module, site_json = utils.get_module(url, handler)
    if not module:
        return 'content handler not found'

    args_copy = args.copy()
    if site_json.get('args'):
        args_copy.update(site_json['args'])

    content = module.test(url, args_copy, site_json, save_debug)
    if 'read' in args:
        return render_template('content.html', content=content)

    return jsonify(content)


@app.route('/audio', methods=['GET'])
def audio():
    args = request.args

    if not args.get('url'):
        return 'No url specified'

    if 'debug' in args:
        save_debug = True
    else:
        save_debug = False

    if args.get('feedhandler'):
        handler = args['feedhandler']
    elif args.get('feedtype'):
        handler = args['feedtype']
    else:
        handler = ''

    module, site_json = utils.get_module(args['url'], handler)
    if not module:
        return 'No content module for this url', 400

    content = module.get_content(args['url'], args, site_json, save_debug)
    if not content.get('_audio'):
        return 'No audio sources found for this url', 204

    if 'novideojs' in args:
        return redirect(content['_audio'])

    if '_audio_key' in content:
        audio_url = config.server + '/videojs-decrypt?src=' + quote_plus(content['_audio']) + '&key=' + content['_audio_key']
    else:
        audio_url = config.server + '/videojs?src=' + quote_plus(content['_audio'])
    if '_audio_type' in content:
        audio_url += '&type=' + quote_plus(content['_audio_type'])
    else:
        audio_url += '&type=audio%2Fmpeg'
    if 'image' in content:
        audio_url += '&poster=' + quote_plus(content['image'])
    elif '_image' in content:
        audio_url += '&poster=' + quote_plus(content['_image'])
    return redirect(audio_url)


@app.route('/video', methods=['GET'])
def video():
    args = request.args
    if not args.get('url'):
        return 'No url specified'
    url = args['url']

    if 'novideojs' in args or 'amp;novideojs' in args:
        novideojs = True
    else:
        novideojs = False

    if 'debug' in args:
        save_debug = True
    else:
        save_debug = False

    if args.get('feedhandler'):
        handler = args['feedhandler']
    elif args.get('feedtype'):
        handler = args['feedtype']
    else:
        handler = ''

    module, site_json = utils.get_module(url, handler)
    if not module:
        return 'No content module for this url'

    content = module.get_content(url, args, site_json, save_debug)
    if not content.get('_video'):
        return 'No video sources found for this url'

    if novideojs:
        print('novideojs')
        if '_video_mp4' in content:
            video_url = content['_video_mp4']
        else:
            video_url = content['_video']
    else:
        video_url = config.server + '/videojs?src=' + quote_plus(content['_video'])
        if content.get('_video_type'):
            video_url += '&type=' + quote_plus(content['_video_type'])
        elif '.m3u8' in content['_video']:
            video_url += '&type=application%2Fx-mpegURL'
        elif '.mp4' in content['_video']:
            video_url += '&type=video%2Fmp4'
        elif '.webm' in content['_video']:
            video_url += '&type=video%2Fwebm'
        if content.get('image'):
            video_url += '&poster=' + quote_plus(content['image'])
        elif content.get('_image'):
            video_url += '&poster=' + quote_plus(content['_image'])

    return redirect(video_url)


@app.route('/videojs')
def videojs():
    # m3u8 test streams: https://test-streams.mux.dev/
    # Big Buck Bunny: https://download.blender.org/peach/bigbuckbunny_movies/
    args = request.args
    video_args = args.copy()
    if not video_args.get('src'):
        return 'No video src specified'

    if not video_args.get('poster'):
        video_args['poster'] = config.server + '/static/video_poster-640x360.webp'

    if not video_args.get('type'):
        if '.mp4' in video_args['src'].lower():
            video_args['type'] = 'video/mp4'
        elif '.webm' in video_args['src'].lower():
            video_args['type'] = 'video/webm'
        elif '.m3u8' in video_args['src'].lower():
            video_args['type'] = 'application/x-mpegURL'
        elif '.mpd' in video_args['src'].lower():
            video_args['type'] = 'application/dash+xml'
        elif '.avi' in video_args['src'].lower():
            video_args['type'] = 'video/x-msvideo'
        elif '.mov' in video_args['src'].lower():
            video_args['type'] = 'video/mp4'
        else:
            video_args['type'] = 'video/mp4'

    if video_args.get('player'):
        if video_args['player'] == 'hlsjs':
            return render_template('video-hlsjs.html', args=video_args)
        elif video_args['player'] == 'shaka':
            return render_template('shaka-player.html', args=video_args)
        elif video_args['player'] == 'vidstack':
            return render_template('video-vidstack.html', args=video_args)
        elif video_args['player'] == 'openplayer':
            return render_template('openplayer.html', args=video_args)
        elif video_args['player'] == 'plyr':
            return render_template('video-plyr.html', args=video_args)
        elif video_args['player'] == 'test':
            return render_template('videojs-test.html', args=video_args)
    return render_template('videojs.html', args=video_args)


@app.route('/videojs-decrypt')
def videojs_decrypt():
    args = request.args
    video_args = args.copy()
    if not video_args.get('src'):
        return 'No video src specified'
    if not video_args.get('key'):
        return 'No decryption key specified'
    if video_args.get('poster'):
        # Make poster image local due to the CORS headers
        video_args['poster'] = '/image?url=' + quote_plus(args['poster']) + '&width=640'
    response = make_response(render_template('videojs-decrypt.html', args=video_args))
    # Need CORS headers headers for ffmpeg.wasm
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    return response


@app.route('/playlist')
def playlist():
    args = request.args
    if args.get('title'):
        title = args['title']
    else:
        title = ''
    if args.get('link'):
        link = args['link']
    else:
        link = ''
    if args.get('tracks'):
        tracks = json.loads(args['tracks'])
        content = None
    elif args.get('url'):
        if 'debug' in args:
            save_debug = True
        else:
            save_debug = False
        module, site_json = utils.get_module(args['url'], handler)
        if not module:
            return 'No content module for this url'
        content = module.get_content(args['url'], args, site_json, save_debug)
        if not content.get('_playlist'):
            return 'No playlist found for this url'
        tracks = content['_playlist']
        if not link:
            link = content['url']
        if not title:
            title = content['title']
    else:
        return 'No playlist tracks or content url given'
    return render_template('playlist.html', tracks=tracks, content=content, title=title, link=link)


@app.route('/debug')
def debug():
    args = request.args
    log_file = None
    if 'n' in args:
        log_file = 'debug.log'
        if int(args['n']) > 0:
            log_file += '.{}'.format(args['n'])

        # Check file exists
        if not os.path.isfile('./debug/' + log_file):
            log_file = None

    if not log_file:
        # By default return the most recent log
        log_file = os.path.basename(max(glob.iglob('./debug/debug.log*'), key=os.path.getctime))

    log = utils.read_file('./debug/' + log_file)
    return render_template('debug.html', title=log_file, content=log)


@app.route('/image')
def image():
    im_io, mimetype = image_utils.get_image(request.args)
    if im_io:
        return send_file(im_io, mimetype=mimetype)
    return mimetype


@app.route('/gallery')
def gallery():
    args = request.args
    if args.get('title'):
        title = args['title']
    else:
        title = ''
    if args.get('link'):
        link = args['link']
    else:
        link = ''
    images = []
    if args.get('images'):
        images = json.loads(args['images'])
    elif args.get('url'):
        if 'debug' in args:
            save_debug = True
        else:
            save_debug = False
        module, site_json = utils.get_module(args['url'], handler)
        if not module:
            return 'No content module for this url'
        args_copy = args.copy()
        if site_json.get('args'):
            args_copy.update(site_json['args'])
        content = module.get_content(args['url'], args_copy, site_json, save_debug)
        if not content.get('_gallery'):
            return 'No gallery sources found for this url'
        images = content['_gallery']
        if not link:
            link = content['url']
        if not title:
            title = content['title']
    if 'desc' in images[0]:
        return render_template('gallery_desc.html', title=title, link=link, images=images)
    return render_template('gallery.html', title=title, link=link, images=images)


@app.route('/map')
def map():
    args = request.args
    if args.get('lat'):
        lat = float(args['lat'])
    else:
        return 'No lat specified'
    if args.get('lon'):
        lon = float(args['lon'])
    else:
        return 'No lon specified'
    if args.get('width'):
        w = int(args['width'])
    else:
        w = 960
    if args.get('height'):
        h = int(args['height'])
    else:
        h = 720
    map = StaticMap(w, h)
    marker = CircleMarker((lon, lat), 'blue', 18)
    map.add_marker(marker)
    if args.get('zoom'):
        image = map.render(zoom=int(args['zoom']))
    else:
        image = map.render()
    im_io = BytesIO()
    image.save(im_io, 'PNG')
    im_io.seek(0)
    return send_file(im_io, mimetype='image/png')


# Make sure playwright browsers are installed
#   playwright install
# Or from script:
# import install_playwright
# from playwright.sync_api import sync_playwright
# with sync_playwright() as p:
#     install_playwright.install(p.webkit)
#     install_playwright.install(p.chromium)
#     install_playwright.install(p.firefox)
#
# async_playwright in Flask example: https://stackoverflow.com/questions/47841985/make-a-python-asyncio-call-from-a-flask-route
async def get_screenshot(url, args):
    async with async_playwright() as playwright:
        # Device emulation: https://playwright.dev/python/docs/emulation
        # https://github.com/microsoft/playwright/blob/main/packages/playwright-core/src/server/deviceDescriptorsSource.json
        if 'device' in args and args['device'] in playwright.devices:
            device = playwright.devices[args['device']]
            browser_name = device['default_browser_type']
        elif 'browser' in args:
            device = None
            browser_name = args['browser']
        else:
            device = None
            browser_name = 'chromium'

        if browser_name == 'chromium' or browser_name == 'chrome':
            engine = playwright.chromium
            if not device:
                device = playwright.devices['Desktop Chrome']
        elif browser_name == 'webkit' or browser_name == 'safari':
            engine = playwright.webkit
            if not device:
                device = playwright.devices['Desktop Safari']
        elif browser_name == 'firefox':
            engine = playwright.firefox
            if not device:
                device = playwright.devices['Desktop Firefox']
        else:
            engine = playwright.chromium
            if not device:
                device = playwright.devices['Desktop Chrome']

        browser = await engine.launch()
        context = await browser.new_context(**device)
        page = await context.new_page()

        if 'networkidle' in args:
            await page.goto(url, wait_until="networkidle")
        else:
            await page.goto(url)

        if 'waitfor' in args:
            await page.wait_for_selector(args['waitfor'])

        if 'waitfortime' in args:
            await page.wait_for_timeout(int(args['waitfortime']))

        if 'locator' in args:
            ss = await page.locator(args['locator']).screenshot()
        else:
            ss = await page.screenshot()

        if not ss:
            await context.close()
            await browser.close()
            return None

        im_io = BytesIO()
        im_io.write(ss)
        im_io.seek(0)

        await context.close()
        await browser.close()
    return im_io


@app.route('/screenshot')
def screenshot():
    args = request.args
    if not args.get('url'):
        return 'No url specified'

    if args.get('provider') and args['provider'] == 'thumbio':
        # https://www.thum.io/documentation/api/url
        # TODO: use https://image.thum.io/get/prefetch/{url} in get_content to prefetch images
        thumb_url = 'https://image.thum.io/get'
        if args.get('maxAge'):
            thumb_url += '/maxAge/' + args['maxAge']
        else:
            thumb_url += '/maxAge/12'
        if args.get('width'):
            thumb_url += '/width/' + args['width']
        else:
            thumb_url += '/width/800'
        if args.get('crop'):
            # Default is 1200
            thumb_url += '/crop/' + args['crop']
        if args.get('allowJPG'):
            thumb_url += '/allowJPG'
        if args.get('png'):
            thumb_url += '/png'
        if args.get('noanimate'):
            thumb_url += '/noanimate'
        thumb_url += '/' + args['url']
        logger.debug('screenshot url ' + thumb_url)
        if 'cropbbox' in args:
            im_args = {
                'url': thumb_url,
                'cropbbox': args['cropbbox']
            }
            im_io, mimetype = image_utils.get_image(im_args)
            if im_io:
                return send_file(im_io, mimetype=mimetype)
        return redirect(thumb_url)
    elif args.get('provider') and args['provider'] == 'pikwy':
        api_url = 'https://api.pikwy.com/?tkn=125&d=3000&u={}&fs=0&w=1280&h=1200&s=100&z=100&f=jpg&rt=jweb'.format(quote_plus(args['url']))
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
            "origin": "https://pikwy.com/",
            "priority": "u=1, i",
            "referrer": "https://pikwy.com/"
        }
        try:
            r = curl_cffi.get(api_url, headers=headers, impersonate="chrome", timeout=30, proxies=config.proxies)
            if r.status_code == 200 and r.json().get('iurl'):
                return redirect(r.json()['iurl'])
        except Exception as e:
            logger.warning('request error {}{} getting {}'.format(e.__class__.__name__, r.status_code, api_url))
            return 'Something went wrong ({})'.format(r.status_code), r.status_code
    elif args.get('provider') and args['provider'] == 'urlto':
        api_url = 'https://api.apilight.com/screenshot/get?url={}&base64=1&width=1366&height=1024&time_allocated=10'.format(quote_plus(args['url']))
        headers = {
            "accept": "text/plain, */*; q=0.01",
            "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
            "origin": "https://urltoscreenshot.com/",
            "priority": "u=1, i",
            "referrer": "https://urltoscreenshot.com/",
            "x-api-key": "j1gIaMwfU545P2ymFWA0gan7yHr7Yla05CJnMheL"
        }
        try:
            r = curl_cffi.get(api_url, headers=headers, impersonate="chrome", timeout=30, proxies=config.proxies)
            if r.status_code == 200:
                return send_file(BytesIO(base64.b64decode(r.content)), mimetype='image/png')
        except Exception as e:
            logger.warning('request error {}{} getting {}'.format(e.__class__.__name__, r.status_code, api_url))
            return 'Something went wrong ({})'.format(r.status_code), r.status_code
    else:
        boundary = '----WebKitFormBoundary' + ''.join(random.sample(string.ascii_letters + string.digits, 16))
        body = '--' + boundary + '\r\nContent-Disposition: form-data; name=\"url\"\r\n\r\n' + args['url'] + '\r\n'
        body += '--' + boundary + '\r\nContent-Disposition: form-data; name=\"pricing\"\r\n\r\nmonthly\r\n'
        body += '--' + boundary + '\r\nContent-Disposition: form-data; name=\"DstFileFormat\"\r\n\r\njpg\r\n'
        body += '--' + boundary + '\r\nContent-Disposition: form-data; name=\"ConversionDelay\"\r\n\r\n0\r\n'
        body += '--' + boundary + '\r\nContent-Disposition: form-data; name=\"CookieConsentBlock\"\r\n\r\ntrue\r\n'
        body += '--' + boundary + '\r\nContent-Disposition: form-data; name=\"Zoom\"\r\n\r\n1\r\n'
        body += '--' + boundary + '\r\nContent-Disposition: form-data; name=\"ParameterPreset\"\r\n\r\nWide\r\n'
        body += '--' + boundary + '--\r\n'
        headers = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
            "cache-control": "no-cache",
            "content-type": "multipart/form-data; boundary=" + boundary,
            "pragma": "no-cache",
            "priority": "u=1, i",
            "x-requested-with": "XMLHttpRequest"
        }
        api_url = 'https://www.web2pdfconvert.com/api/convert/web/to/jpg?storefile=true&filename=' + urlsplit(args['url']).path[1:].replace('/', '-')
        r = curl_cffi.post(api_url, data=body, headers=headers, impersonate="chrome", timeout=30, proxies=config.proxies)
        if r.status_code == 200:
            return redirect(r.json()['Files'][0]['Url'])
        else:
            logger.warning('screenshot error {} getting {}'.format(r.status_code, api_url))
            return 'Something went wrong ({})'.format(r.status_code), r.status_code
        # except Exception as e:
        #     logger.warning('request error {}{} getting {}'.format(e.__class__.__name__, r.status_code, api_url))
        #     return 'Something went wrong ({})'.format(r.status_code), r.status_code

    # # https://github.com/microsoft/playwright-python/issues/723
    # loop = asyncio.ProactorEventLoop()
    # asyncio.set_event_loop(loop)
    # ss_io = loop.run_until_complete(get_screenshot(args['url'], args))
    # if not ss_io:
    #     return 'Something went wrong'
    # return send_file(ss_io, mimetype='image/png')


@app.route('/send_src')
def send_src():
    args = request.args
    if 'src' not in args:
        return None
    r = requests.get(args['src'])
    if r.status_code != 200:
        return 'Something went wrong'
    f_io = BytesIO(r.content)
    return send_file(f_io, mimetype='text/html')

# This is to bypass video content restricted by CORS (Access-Control-Allow-Origin) headers
# https://github.com/ChopsKingsland/cors-proxy/blob/master/app.py
@app.route('/<path:url>', methods=['GET'])
def proxy(url):
    m = re.search(r'^https?://[^/]+/proxy/(.*)', request.url)
    if not m:
        return 'Hello! You must be lost :('
    proxy_url = m.group(1)
    logger.debug('proxy url: ' + proxy_url)
    headers = None

    if 'drive.google.com/' in proxy_url:
        # Google drive videos need to be requested with the headers & cookies
        content = google.get_content(proxy_url, {}, {"module": "google"}, False)
        if content and '_video' in content:
            proxy_url = content['_video']
            if '_video_headers' in content:
                headers = content['_video_headers']

    if 'manifest.googlevideo.com/api' in proxy_url:
        # headers = {
        #     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        #     "Accept-Language": "en-us,en;q=0.5",
        #     "Sec-Fetch-Mode": "navigate",
        #     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.24 Safari/537.36",
        # }
        # cookies = []
        # for key, val in config.youtube_cookies.items():
        #     cookies.append('{}={}'.format(key, val))
        # headers['Cookie'] = "; ".join(cookies)
        # Force IPV4
        # https://github.com/yt-dlp/yt-dlp/issues/11868
        # https://stackoverflow.com/questions/33046733/force-requests-to-use-ipv4-ipv6
        requests.packages.urllib3.util.connection.HAS_IPV6 = False
        #print(headers)

    if 'tt_chain_token' in proxy_url:
        # For TikTok videos, need to add a cookie
        # https://github.com/yt-dlp/yt-dlp/issues/9997#issuecomment-2175010516
        m = re.search(r'tk=tt_chain_token_([^&]+)', proxy_url)
        token = m.group(1)
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.74 Safari/537.36",
            "Cookie": "tk={};".format(token)
        }
        proxy_url = proxy_url.replace('tt_chain_token_' + token, 'tk')

    if '.m3u8' in proxy_url and not proxy_url.endswith('.ts'):
        # This doen't reliably work for youtube m3u8 urls. They return 403 for methods here, but work fine in the console or module
        # r = requests.get(proxy_url, headers=headers)
        if 'manifest.googlevideo.com/api' in proxy_url:
            r = curl_cffi.get(proxy_url, impersonate='safari', proxies=config.proxies)
        elif 'cdn.rasset.ie' in proxy_url:
            r = curl_cffi.get(proxy_url, impersonate='chrome')
        elif headers:
            # r = curl_cffi.get(proxy_url, headers=headers, impersonate=config.impersonate, proxies=config.proxies)
            r = requests.get(proxy_url, headers=headers)
        else:
            # r = curl_cffi.get(proxy_url, impersonate=config.impersonate, proxies=config.proxies)
            r = requests.get(proxy_url)
        if r.status_code != 200:
            logger.warning('requests error {} getting {}'.format(r.status_code, proxy_url))
            if r.text:
                f_io = BytesIO(r.text.encode())
                return send_file(f_io, mimetype='text/plain'), r.status_code
            return 'Something went wrong ({})'.format(r.status_code), r.status_code
        m3u8_playlist = r.text
        # Rewrite playlist files to proxy the contents
        if 'cdn.rasset.ie' in proxy_url:
            m3u8_playlist = m3u8_playlist.replace('/hls-vod', config.server + '/proxy/https://cdn.rasset.ie/hls-vod')
        else:
            m3u8_playlist = m3u8_playlist.replace('https://', config.server + '/proxy/https://')
        f_io = BytesIO(m3u8_playlist.encode())
        return send_file(f_io, mimetype='text/plain')

    # r = requests.get(proxy_url, headers=headers, stream=True)
    if headers:
        r = curl_cffi.get(proxy_url, headers=headers, impersonate=config.impersonate, proxies=config.proxies, stream=True)
    else:
        r = curl_cffi.get(proxy_url, impersonate=config.impersonate, proxies=config.proxies, stream=True)
    # Note on chunk size: https://stackoverflow.com/questions/34229349/flask-streaming-file-with-stream-with-context-is-very-slow
    resp = Response(stream_with_context(r.iter_content(chunk_size=1024)), status=r.status_code)
    resp.headers['Content-Type'] = r.headers['content-type']
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/stream_spotify')
def stream_spotify():
    args = request.args
    if not args.get('url'):
        return 'No url specified'
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    content_id = paths[-1]
    content_type = paths[-2]
    if content_type != 'episode':
        return 'Content not supported'
    tokens = spotify.get_tokens()
    if not tokens:
        return 'unable to get Spotify access tokens'

    headers = {
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "authorization": 'Bearer ' + tokens['access_token']['accessToken'],
        "content-type": "application/json",
        "origin": "https://open.spotify.com",
        "priority": "u=1, i",
        "referer": "https://open.spotify.com/",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"131\", \"Chromium\";v=\"131\", \"Not_A Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
    }
    url = 'https://spclient.wg.spotify.com/soundfinder/v1/unauth/episode/{}/com.widevine.alpha'.format(content_id)
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        return 'Error {} getting {}'.format(r.status_code, url)
    widevine = r.json()
    utils.write_file(widevine, './debug/widevine.json')

    if widevine.get('url'):
        audio_file = widevine['url'][0]
    else:
        params = {
            'version': 10000000,
            'product': 9,
            'platform': 39,
            'alt': 'json'
        }
        headers['TE'] = 'Trailers'
        url = 'https://gew1-spclient.spotify.com/storage-resolve/v2/files/audio/interactive/11/' + widevine['fileId']
        r = requests.get(url, params=params, headers=headers)
        if r.status_code != 200:
            return 'Error {} getting {}'.format(r.status_code, url)
        spotify_files = r.json()
        utils.write_file(spotify_files, './debug/spotify_files.json')
        audio_file = spotify_files['cdnurl'][0]
    print(audio_file)

    if 'key' in args:
        if args['key'] == '':
            key = 'deadbeefdeadbeefdeadbeefdeadbeef'
        else:
            key = args['key']
    else:
        key = spotify.get_key(widevine['fileId'])

    # TODO: play with videojs-contrib-eme or shaka-player?

    if True:
        video_args = {
            "key": key,
            "src": audio_file,
            "type": "audio/mp4",
            "poster": args['poster'] if 'poster' in args else config.server + '/static/video_poster-640x360.webp'
        }
        response = make_response(render_template('videojs-decrypt.html', args=video_args))
        # required headers for ffmpeg.wasm
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
        return response

    # Decrypt and stream
    # https://gist.github.com/anthonyeden/f3b3bdf6f62badd8f87bb574283f488a
    # Other formats?
    # Can't ffwd/rewind?
    # mime_type = 'audio/mpeg'
    # ffmpeg_cmd = ['ffmpeg', '-decryption_key', key, '-i', audio_file, '-f', 'mp3', '-']
    # mime_type = 'audio/aac'
    # ffmpeg_cmd = ['ffmpeg', '-decryption_key', key, '-i', audio_file, '-c:a', 'aac', '-f', 'adts', '-']
    # process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=-1)
    mime_type = 'audio/mp4'
    ffmpeg_cmd = ['ffmpeg', '-decryption_key', key, '-i', audio_file, '-c', 'copy', '-']
    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, err = process.communicate()
    return send_file(io.BytesIO(out), mimetype=mime_type)
    # def generate():
    #     nonlocal process
    #     startTime = time.time()
    #     buffer = []
    #     sentBurst = False
    #     try:
    #         while True:
    #             # Get some data from ffmpeg
    #             line = process.stdout.read(1024)
    #             # We buffer everything before outputting it
    #             buffer.append(line)
    #             # Minimum buffer time, 3 seconds
    #             if sentBurst is False and time.time() > startTime + 3 and len(buffer) > 0:
    #                 sentBurst = True
    #                 for i in range(0, len(buffer) - 2):
    #                     print('Send initial burst #{}'.format(i))
    #                     yield buffer.pop(0)
    #             elif time.time() > startTime + 3 and len(buffer) > 0:
    #                 yield buffer.pop(0)
    #             process.poll()
    #             if isinstance(process.returncode, int):
    #                 if process.returncode > 0:
    #                     print('FFmpeg Error {}'.format(process.returncode))
    #                 break
    #     except GeneratorExit:
    #         print('stream_spotify GeneratorExit')
    #         process.kill()
    # response = Response(stream_with_context(generate()), mimetype=mime_type)
    # @response.call_on_close
    # def on_close():
    #     nonlocal process
    #     print('stream_spotify on_close')
    #     if process:
    #         process.kill()
    # # GeneratorExit/on_close don't get triggered when window is closed so the process doen't get killed
    # return response


@app.route('/')
def home():
    return 'Hello! You must be lost :('


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
