import glob, importlib, os, requests, sys
import logging, logging.handlers
from flask import Flask, jsonify, render_template, redirect, request, send_file
from io import BytesIO
from PIL import Image
from urllib.parse import urlsplit

import utils
from feedhandlers import *
from sites import handlers

# Test: https://buoyantunrealisticmodule.m4rk4.repl.co/feed?feedtype=wp-posts&url=https%3A%2F%2Fliliputing.com%2Fwp-json%2Fwp%2Fv2%2Fposts%3Fper_page%3D3&title=Liliputing&exc_filters=%7B%22tags%22%3A%20%22%2Fdeals%2Fi%22%7D

app = Flask(__name__)

# Setup logger
LOG_FILENAME = './debug/debug.log'
handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=100*1024, backupCount=3)
logging.basicConfig(
  level = logging.DEBUG,
  format = "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
  datefmt = '%Y-%m-%dT%H:%M:%S',
  handlers = [handler, logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Turn off debuging in some modules
logging.getLogger('pytube').setLevel(logging.WARNING)
logging.getLogger('snscrape').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

def get_module(args):
  module = None
  if args.get('url'):
    split_url = urlsplit(args['url'])
    split_loc = split_url.netloc.split('.')
    domain = '.'.join(split_loc[-2:])
    if domain == 'feedburner.com':
      domain = split_url.path.split('/')[1]
    if handlers.get(domain):
      try:
        module_name = '.{}'.format(handlers[domain]['module'])
        module = importlib.import_module(module_name, 'feedhandlers')
      except:
        logger.warning('unable to load module ' + module_name)
        module = None
    else:
      logger.warning('unknown feedhandler module for domain ' + domain)

  if not module:
    feedhandler = ''
    if args.get('feedhandler'):
      feedhandler = args['feedhandler']
    elif args.get('feedtype'):
      feedhandler = args['feedtype']
    elif args.get('url') and 'wp-json' in args['url']:
      feedhandler = 'wp_posts'
    if feedhandler:
      if feedhandler == 'wp-posts':
        feedhandler = 'wp_posts'
      try:
        module_name = '.{}'.format(feedhandler)
        module = importlib.import_module(module_name, 'feedhandlers')
      except:
        logger.warning('unable to load module ' + module_name)
        module = None

  return module

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

  module = get_module(args)
  if module:
    feed = module.get_feed(args, save_debug)
    if not feed:
      return 'No feed found'
    feed['feed_url'] = request.url
    return jsonify(feed)
  return 'Something went wrong :(' 

@app.route('/content', methods=['GET'])
def content():
  args = request.args
  if 'debug' in args:
    save_debug = True
  else:
    save_debug = False

  module = get_module(args)
  if module:
    content = module.get_content(args['url'], args, save_debug)
    if 'json' in args:
      return jsonify(content)
    else:
      return render_template('content.html', content=content)
  return 'Something went wrong :(' 

@app.route('/audio', methods=['GET'])
def audio():
  args = request.args

  if not args.get('url'):
    return 'No url specified'

  if 'debug' in args:
    save_debug = True
  else:
    save_debug = False

  module = get_module(args)
  if not module:
    return 'No content module for this url'

  content = module.get_content(args['url'], args, save_debug)
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

  module = get_module(args)
  if not module:
    return 'No content module for this url'

  content = module.get_content(args['url'], args, save_debug)
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

  with open('./debug/' + log_file, 'r') as f:
    log = f.read()
  return render_template('debug.html', title=log_file, content=log)

@app.route('/instagram')
def instagram():
  args = request.args
  if 'debug' in args:
    save_debug = True
  else:
    save_debug = False

  if 'url' in args:
    content_html = utils.add_instagram(args['url'], save_debug)
  else:
    content_html = '<h2>Missing url</h2>'
  return render_template('instagram.html', title=args['url'], content=content_html)

@app.route('/image')
def image():
  args = request.args
  if not 'url' in args:
    return 'No url given'

  height = 0
  if 'height' in args:
    height = int(args['height'])
  width = 0
  if 'width' in args:
    width = int(args['width'])
  scale = 0
  if 'scale' in args:
    scale = int(args['scale'])

  try:
    r = requests.get(args['url'])
    im_io = BytesIO(r.content)
    im = Image.open(im_io)
  except:
    im = None

  if not im:
    return 'Something went wrong :('

  mimetype = im.get_format_mimetype()

  if scale > 0:
    h = (im.height * scale) // 100
    w = (im.width * scale) // 100
  elif height > 0 and width == 0:
    h = height
    w = (im.width * height) // im.height
  elif height == 0 and width > 0:
    h = (im.height * width) // im.width
    w = width
  else:
    h = im.height
    w = im.width

  save = False
  if h != im.height or w != im.width:
    #im.thumbnail((h, w))
    im = im.resize((w, h), resample=Image.LANCZOS)
    save = True

  if 'overlay' in args:
    if args['overlay'] == 'video':
      overlay_sizes = [{"width": 512, "height": 360, "name": "video_play_button-512x360.png"},
                       {"width": 384, "height": 270, "name": "video_play_button-384x270.png"},
                       {"width": 256, "height": 180, "name": "video_play_button-256x180.png"},
                       {"width": 192, "height": 135, "name": "video_play_button-192x135.png"},
                       {"width": 128, "height": 90, "name": "video_play_button-128x90.png"},
                       {"width": 97, "height": 68, "name": "video_play_button-97x68.png"},
                       {"width": 64, "height": 45, "name": "video_play_button-64x45.png"},
                       {"width": 48, "height": 34, "name": "video_play_button-48x34.png"}]
    else:
      overlay_sizes = [{"width": 512, "height": 512, "name": "play_button-512x512.png"},
                       {"width": 384, "height": 384, "name": "play_button-384x384.png"},
                       {"width": 256, "height": 256, "name": "play_button-256x256.png"},
                       {"width": 192, "height": 192, "name": "play_button-192x192.png"},
                       {"width": 128, "height": 128, "name": "play_button-128x128.png"},
                       {"width": 96, "height": 96, "name": "play_button-96x96.png"},
                       {"width": 64, "height": 64, "name": "play_button-64x64.png"},
                       {"width": 48, "height": 48, "name": "play_button-48x48.png"}]

    w_size = utils.closest_dict(overlay_sizes, 'width', w//3)
    h_size = utils.closest_dict(overlay_sizes, 'height', h//3)
    if h_size['width'] <= w_size['width']:
      overlay_name = h_size['name']
    else:
      overlay_name = w_size['name']
    #im_overlay = Image.open(requests.get('https://icons.iconarchive.com/icons/iconsmind/outline/{}/Youtube-icon.png'.format(size), stream=True).raw)
    im_overlay = Image.open('./static/' + overlay_name)
    x = (w - im_overlay.width) // 2
    y = (h - im_overlay.height) // 2
    im.paste(im_overlay, (x, y), mask=im_overlay)
    save = True

  if save:
    im_io = BytesIO()
    im.save(im_io, 'JPEG', quality=70)
    mimetype = 'image/jpeg'

  im_io.seek(0)
  return send_file(im_io, mimetype=mimetype)

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=8080)