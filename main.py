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

@app.route('/redirect', methods=['GET'])
def av_redirect():
  args = request.args
  if 'debug' in args:
    save_debug = True
  else:
    save_debug = False

  module = get_module(args)
  if module:
    content = module.get_content(args['url'], args, save_debug)
    if 'video' in args:
      return redirect(content['_video'])
    elif 'audio' in args:
      return redirect(content['_audio'])
    elif content.get('_video'):
      return redirect(content['_video'])
    elif content.get('_audio'):
      return redirect(content['_audio'])
  return 'No audio or video sources found for <a href="{0}">{0}</a>'.format(args['url'])

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

@app.route('/video')
def video():
  args = request.args
  if 'debug' in args:
    save_debug = True
  else:
    save_debug = False

  video_args = {}
  if 'src' in args:
    video_args['src'] = args['src']
  elif 'url' in args:
    video_args['src'] = args['src']
  else:
    return 'No video src/url found'

  if 'poster' in args:
    video_args['poster'] = args['poster']
  else:
    video_args['poster'] = '/static/video_poster-640x360.webp'

  if 'video_type' in args:
    video_args['video_type'] = args['video_type']
  else:
    video_args['video_type'] = 'none'

  if video_args['video_type'] == 'video/mp4' or '.mp4' in video_args['src'].lower():
    video_args['video_type'] = 'video/mp4'
    return render_template('video.html', args=video_args)

  elif video_args['video_type'] == 'video/webm' or '.webm' in video_args['src'].lower():
    video_args['video_type'] = 'video/webm'
    return render_template('video.html', args=video_args)

  elif video_args['video_type'] == 'application/x-mpegURL' or '.m3u8' in video_args['src'].lower():
    video_args['video_type'] = 'application/x-mpegURL'
    return render_template('videojs.html', args=video_args)

  elif 'vimeo.com' in video_args['src'].lower():
    content = vimeo.get_content(video_args['src'], None, save_debug)
    if content:
      video_args['src'] = content['_video']
      video_args['poster'] = content['_image']
      video_args['video_type'] = 'video/mp4'
      return render_template('video.html', args=video_args)

  elif 'youtube' in video_args['src'].lower():
    content = youtube.get_content(video_args['src'], None, save_debug)
    if content:
      video_args['src'] = content['_video']
      video_args['poster'] = content['_image']
      if 'mp4' in content['_video']:
        video_args['video_type'] = 'video/mp4'
      elif 'webm' in content['_video']:
        video_args['video_type'] = 'video/webm'
      return render_template('video.html', args=video_args)

  return 'Unknown video type'

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

  h = 0
  if 'height' in args:
    h = int(args['height'])
  w = 0
  if 'width' in args:
    w = int(args['width'])
  s = 0
  if 'scale' in args:
    s = int(args['scale'])

  try:
    img = Image.open(requests.get(args['url'], stream=True).raw)
  except:
    img = None
  if not img:
    return 'Something went wrong :('

  img_h, img_w = img.size
  if s > 0:
    h = img_h // s
    w = img_w // s
  elif h > 0 and w == 0:
    w = (img_w * h) // img_h
  elif h == 0 and w > 0:
    h = (img_h * w) // img_w
  else:
    h = img_h
    w = img_w

  img.thumbnail((h, w))
  img_io = BytesIO()
  img.save(img_io, 'JPEG', quality=70)
  img_io.seek(0)
  return send_file(img_io, mimetype='image/jpeg')

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=8080)