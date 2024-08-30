import glob, importlib, io, json, os, re, requests, sys
import logging, logging.handlers
from curl_cffi import Curl, CurlInfo, CurlOpt
from flask import Flask, jsonify, render_template, redirect, Response, request, send_file, stream_with_context
from flask_cors import CORS
from io import BytesIO
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from staticmap import StaticMap, CircleMarker
from urllib.parse import parse_qs, quote, quote_plus, urlsplit

import config, image_utils, utils
from feedhandlers import ytdl

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
        return 'No content module for this url'

    content = module.get_content(args['url'], args, site_json, save_debug)
    if not content.get('_audio'):
        return 'No audio sources found for this url'

    return redirect(content['_audio'])


@app.route('/video', methods=['GET'])
def video():
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
        return 'No content module for this url'

    content = module.get_content(args['url'], args, site_json, save_debug)
    if not content.get('_video'):
        return 'No video sources found for this url'

    if 'novideojs' in args:
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
    args = request.args
    video_args = args.copy()
    if not video_args.get('src'):
        return 'No video src specified'

    # if 'www.youtube.com' in video_args['src']:
    #     return render_template('videojs-youtube.html', args=video_args)

    if not video_args.get('poster'):
        video_args['poster'] = config.server + '/static/video_poster-640x360.webp'

    if not video_args.get('type'):
        if '.mp4' in video_args['src'].lower():
            video_args['type'] = 'video/mp4'
        elif '.webm' in video_args['src'].lower():
            video_args['type'] = 'video/webm'
        elif '.m3u8' in video_args['src'].lower():
            video_args['type'] = 'application/x-mpegURL'
        else:
            video_args['type'] = 'video/mp4'

    # return render_template('videojs-test.html', args=video_args)
    return render_template('videojs.html', args=video_args)


@app.route('/openplayer')
def openplayer():
    args = request.args
    player_args = args.copy()
    if player_args.get('url'):
        item = utils.get_content(player_args['url'], {}, False)
        if not item:
            return 'Unable to get url content'
        if player_args.get('content_type'):
            if player_args['content_type'] == 'video':
                player_args['src'] = item['_video']
            elif player_args['content_type'] == 'audio':
                player_args['src'] = item['_audio']
        else:
            if item.get('_video'):
                player_args['src'] = item['_video']
            elif item.get('_audio'):
                player_args['src'] = item['_audio']

    if not player_args.get('src'):
        return 'No player source was found'

    if not player_args.get('poster'):
        player_args['poster'] = '/static/video_poster-640x360.webp'

    if not player_args.get('src_type'):
        if '.mp4' in player_args['src'].lower():
            player_args['src_type'] = 'video/mp4'
        elif '.webm' in player_args['src'].lower():
            player_args['src_type'] = 'video/webm'
        elif '.m3u8' in player_args['src'].lower():
            player_args['src_type'] = 'application/x-mpegURL'
        else:
            player_args['src_type'] = 'video/mp4'

    return render_template('openplayer.html', args=player_args)


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
        content = module.get_content(args['url'], args, site_json, save_debug)
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
        w = 800
    if args.get('height'):
        h = int(args['height'])
    else:
        h = 400
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


@app.route('/screenshot')
def screenshot():
    # Make sure playwright browsers are installed
    #   playwright install
    # Or from script:
    # import install_playwright
    # from playwright.sync_api import sync_playwright
    # with sync_playwright() as p:
    #     install_playwright.install(p.webkit)
    #     install_playwright.install(p.chromium)
    #     install_playwright.install(p.firefox)
    args = request.args
    if not args.get('url'):
        return 'No url specified'
    if 'width' in args:
        width = int(args['width'])
    else:
        width = 800
    if 'height' in args:
        height = int(args['height'])
    else:
        height = 800
    with sync_playwright() as playwright:
        engine = None
        if 'browser' in args:
            if args['browser'] == 'chrome' or args['browser'] == 'chromium':
                engine = playwright.chromium
            elif args['browser'] == 'firefox':
                engine = playwright.firefox
        if not engine:
            engine = playwright.webkit
        browser = engine.launch()
        context = browser.new_context(viewport={"width": width, "height": height}, ignore_https_errors=True)
        page = context.new_page()
        if args.get('networkidle'):
            page.goto(args['url'], wait_until="networkidle")
        else:
            page.goto(args['url'])
        if args.get('waitfor'):
            page.wait_for_selector(args['waitfor'])
        if args.get('waitfortime'):
            page.wait_for_timeout(int(args['waitfortime']))
        if args.get('locator'):
            ss = page.locator(args['locator']).screenshot()
        else:
            ss = page.screenshot()
    if not ss:
        return 'Something went wrong'
    im_io = BytesIO()
    im_io.write(ss)
    im_io.seek(0)
    return send_file(im_io, mimetype='image/png')


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
    headers = {}

    if 'www.youtube.com/watch' in proxy_url:
        content = ytdl.get_content(proxy_url, {"player_client": "mediaconnect"}, {"module": "ytdl"}, False)
        if content and '_m3u8' in content:
            f_io = BytesIO(content['_m3u8'].encode())
            return send_file(f_io, mimetype='text/html')

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

    if '.m3u8' in proxy_url:
        r = requests.get(proxy_url, headers=headers)
        if r.status_code != 200:
            logger.warning('requests error {} getting {}'.format(r.status_code, proxy_url))
            if r.text:
                f_io = BytesIO(r.text.encode())
                return send_file(f_io, mimetype='text/html')
            return 'Something went wrong ({})'.format(r.status_code), r.status_code
        m3u8_playlist = r.text
        # Rewrite playlist files to proxy the contents
        m3u8_playlist = m3u8_playlist.replace('https://', config.server + '/proxy/https://')
        f_io = BytesIO(m3u8_playlist.encode())
        return send_file(f_io, mimetype='text/html')
        if False:
            buffer = BytesIO()
            c = Curl()
            c.setopt(CurlOpt.WRITEDATA, buffer)
            # c.setopt(CurlOpt.PROXY, config.http_proxy.encode())
            c.setopt(CurlOpt.CAINFO, config.verify_path.encode())
            c.setopt(CurlOpt.URL, proxy_url.encode())
            if 'xxx-googlevideo.com' in proxy_url:
                headers = [
                    b"Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    b"Accept-Language: en-us,en;q=0.5",
                    b"Sec-Fetch-Mode: navigate",
                    b"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.15 Safari/537.36"
                ]
                c.setopt(CurlOpt.HTTPHEADER, headers)
            c.impersonate(config.impersonate)
            try:
                c.perform()
            except Exception as e:
                logger.warning('exception {} getting {}'.format(e.__class__.__name__, proxy_url))
                return 'Something went wrong', 500
            status_code = c.getinfo(CurlInfo.RESPONSE_CODE)
            c.close()
            if status_code == 200:
                m3u8_playlist = buffer.getvalue().decode()
                m3u8_playlist = m3u8_playlist.replace('https://', config.server + '/proxy/https://')
                f_io = BytesIO(m3u8_playlist.encode())
                return send_file(f_io, mimetype='text/html')
            return 'Something went wrong ({})'.format(status_code), status_code

    r = requests.get(proxy_url, headers=headers, stream=True)
    # Note on chunk size: https://stackoverflow.com/questions/34229349/flask-streaming-file-with-stream-with-context-is-very-slow
    resp = Response(stream_with_context(r.iter_content(chunk_size=1024)), content_type=r.headers['content-type'], status=r.status_code)
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/')
def home():
    return 'Hello! You must be lost :('


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
