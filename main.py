import glob, importlib, io, os, requests, sys
import logging, logging.handlers
from flask import Flask, jsonify, render_template, redirect, request, send_file
from flask_cors import CORS
from io import BytesIO
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from staticmap import StaticMap, CircleMarker
from urllib.parse import quote

import image_utils, utils

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


@app.route('/')
def home():
    return 'Hello! You must be lost :('


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


@app.route('/test', methods=['GET'])
def test():
    args = request.args
    feed = utils.read_json_file('./debug/test.json')
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
        return 'No audio sources found for this url'

    return redirect(content['_video'])


@app.route('/videojs')
def videojs():
    args = request.args
    video_args = args.copy()
    if not video_args.get('src'):
        return 'No video src specified'

    if not video_args.get('poster'):
        video_args['poster'] = 'https://BuoyantUnrealisticModule.m4rk4.repl.co/static/video_poster-640x360.webp'

    if not video_args.get('type'):
        if '.mp4' in video_args['src'].lower():
            video_args['type'] = 'video/mp4'
        elif '.webm' in video_args['src'].lower():
            video_args['type'] = 'video/webm'
        elif '.m3u8' in video_args['src'].lower():
            video_args['type'] = 'application/x-mpegURL'
        else:
            video_args['type'] = 'video/mp4'

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
        page.goto(args['url'])
        #page.goto(args['url'], wait_until="networkidle")
        #page.waitForLoadState('domcontentloaded')
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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
