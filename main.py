import av, glob, os, requests, sys
import logging, logging.handlers
from flask import Flask, jsonify, render_template, redirect, request, send_file
from io import BytesIO
from PIL import Image, ImageDraw
from urllib.parse import quote_plus

import image_utils, utils

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
logging.getLogger('chardet').setLevel(logging.WARNING)
logging.getLogger('filelock').setLevel(logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('pytube').setLevel(logging.WARNING)
logging.getLogger('snscrape').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

@app.template_filter()
def make_thumbnail(img_src):
  return '/image?url={}&height=100&crop=120,100'.format(quote_plus(img_src))

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

  module = utils.get_module(url, handler)
  if not module:
    return 'feed handler not found'

  feed = module.get_feed(args, save_debug)
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

  module = utils.get_module(url, handler)
  if not module:
    return 'content handler not found'

  content = module.get_content(url, args, save_debug)
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

  module = utils.get_module(args['url'], handler)
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

  if args.get('feedhandler'):
    handler = args['feedhandler']
  elif args.get('feedtype'):
    handler = args['feedtype']
  else:
    handler = ''

  module = utils.get_module(args['url'], handler)
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

@app.route('/image')
def image():
  im_io, mimetype = image_utils.get_image(request.args)
  if im_io:
    return send_file(im_io, mimetype=mimetype)
  return mimetype

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=8080)