import glob, os, re, requests, sys
import logging, logging.handlers
from flask import Flask, jsonify, render_template, redirect, request, send_file
from io import BytesIO
from PIL import Image, ImageDraw

import utils

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
logging.getLogger('filelock').setLevel(logging.WARNING)
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('pytube').setLevel(logging.WARNING)
logging.getLogger('snscrape').setLevel(logging.WARNING)
logging.getLogger('tldextract').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

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

  if args.get('feedhandler'):
    handler = args['feedhandler']
  elif args.get('feedtype'):
    handler = args['feedtype']
  else:
    handler = ''

  url = args.get('url')

  module = utils.get_module(url, handler)
  if module:
    #if not re.search(r'espn\.com|vidible\.tv|vimeo\.com|youtube\.com', url):
    #  url = utils.clean_url(url)
    content = module.get_content(url, args, save_debug)
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
  im = None
  args = request.args
  if not 'url' in args:
    w = -1
    h = -1
    if args.get('width'):
      w = int(args['width'])
    if args.get('height'):
      h = int(args['height'])
    if w > 0 and h < 0:
      h = w
    elif w < 0 and h > 0:
      w = h
    if w > 0 and h > 0:
      color = 'SlateGray'
      if args.get('color'):
        if args['color'].count(',') == 0:
          color = args['color']
        else:
          r, g, b = args['color'].split(',')
          color = (int(r), int(g), int(b))
      if color == 'none':
        im = Image.new('RGBA', (w, h), color=(0,0,0,0))
        mimetype = 'image/png'
      else:
        im = Image.new('RGB', (w, h), color=color)
        mimetype = 'image/jpg'
    else:
      return 'No url given'

  if not im:
    try:
      #im_overlay = Image.open(requests.get(args['url'].format(size), stream=True).raw)
      r = requests.get(args['url'])
      if r.status_code == 200:
        im_io = BytesIO(r.content)
        im = Image.open(im_io)
        mimetype = im.get_format_mimetype()
    except:
      im = None

  if not im:
    return 'Something went wrong :('

  if im.mode == 'P':
    im = im.convert('RGBA')

  w = im.width
  h = im.height

  # Do operations in the order of the args
  resized = False
  save = False
  for arg, val in args.items():
    # Resize specify scale or width and/or height
    if (arg == 'height' or arg == 'width' or arg == 'scale') and resized == False:
      if arg == 'scale':
        h = (im.height * int(val)) // 100
        w = (im.width * int(val)) // 100
      elif args.get('width') and args.get('height'):
        w = int(args['width'])
        h = int(args['height'])
      elif args.get('width'):
        w = int(args['width'])
        h = (im.height * w) // im.width
      elif args.get('height'):
        h = int(args['height'])
        w = (im.width * h) // im.height
      im = im.resize((w, h), resample=Image.LANCZOS)
      resized = True
      save = True

    elif arg == 'crop':
      crop_args = args['crop'].split(',')
      if len(crop_args) == 4:
        # Rectangle
        x = int(crop_args[0])
        y = int(crop_args[1])
        w = min(int(crop_args[2]), im.width - x)
        h = min(int(crop_args[3]), im.height - y)
      elif len(crop_args) == 2:
        # Centered rectangle
        w = int(crop_args[0])
        h = int(crop_args[1])
        x = (im.width - w) // 2
        y = (im.height - h) // 2
      elif len(crop_args) == 1:
        # Square
        w = int(crop_args[0])
        h = w
        x = (im.width - w) // 2
        y = (im.height - h) // 2
      im = im.crop((x, y, x + w, y + h))
      save = True

    elif arg == 'overlay':
      im_overlay = None
      if val == 'video':
        overlays = [{"width": 512, "height": 360, "url": "./static/video_play_button-512x360.png"},
                    {"width": 384, "height": 270, "url": "./static/video_play_button-384x270.png"},
                    {"width": 256, "height": 180, "url": "./static/video_play_button-256x180.png"},
                    {"width": 192, "height": 135, "url": "./static/video_play_button-192x135.png"},
                    {"width": 128, "height": 90, "url": "./static/video_play_button-128x90.png"},
                    {"width": 97, "height": 68, "url": "./static/video_play_button-97x68.png"},
                    {"width": 64, "height": 45, "url": "./static/video_play_button-64x45.png"},
                    {"width": 48, "height": 34, "url": "./static/video_play_button-48x34.png"}]
        overlay = utils.closest_dict(overlays, 'height', h // 5)
        im_overlay = Image.open(overlay['url'])
      elif val == 'audio':
        overlays = [{"width": 512, "height": 512, "url": "./static/play_button-512x512.png"},
                    {"width": 384, "height": 384, "url": "./static/play_button-384x384.png"},
                    {"width": 256, "height": 256, "url": "./static/play_button-256x256.png"},
                    {"width": 192, "height": 192, "url": "./static/play_button-192x192.png"},
                    {"width": 128, "height": 128, "url": "./static/play_button-128x128.png"},
                    {"width": 96, "height": 96, "url": "./static/play_button-96x96.png"},
                    {"width": 64, "height": 64, "url": "./static/play_button-64x64.png"},
                    {"width": 48, "height": 48, "url": "./static/play_button-48x48.png"},
                    {"width": 32, "height": 32, "url": "./static/play_button-32x32.png"}]
        overlay = utils.closest_dict(overlays, 'height', h // 5)
        im_overlay = Image.open(overlay['url'])
      elif val.startswith('http'):
        r = requests.get(val)
        if r.status_code == 200:
          io_overlay = BytesIO(r.content)
          im_overlay = Image.open(io_overlay)
      if im_overlay:
        x = (w - im_overlay.width) // 2
        y = (h - im_overlay.height) // 2
        im.paste(im_overlay, (x, y), mask=im_overlay)
        save = True

    elif arg == 'mask':
      if val == 'ellipse':
        # Credit to: https://stackoverflow.com/questions/890051/how-do-i-generate-circular-thumbnails-with-pil
        mask_size = (3*w, 3*h)
        mask = Image.new('L', mask_size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse([(0,0), mask_size], fill=255)
        mask = mask.resize(im.size, Image.ANTIALIAS)
        im.putalpha(mask)
        mimetype = 'image/png'
        save = True

    elif arg == 'border':
      b = int(val)
      color = (0,0,0,0)
      if 'color' in args:
        if args.get('color'):
          color = tuple(map(int, args['color'][1:-1].split(',')))
      if len(color) < 3 or len(color) > 4:
        color = (0,0,0,0)
      if len(color) == 4:
        new_im = Image.new("RGBA", (w + 2*b, h + 2*b), color)
      else:
        new_im = Image.new("RGB", (w + 2*b, h + 2*b), color)
      new_im.paste(im, (b, b))
      im = new_im
      mimetype = 'image/png'
      save = True

  if save:
    im_io = BytesIO()
    print(im.mode)
    if im.mode in ['RGBA', 'P']:
      im.save(im_io, 'PNG')
      mimetype = 'image/png'
    else:
      im.save(im_io, 'JPEG')
      mimetype = 'image/jpeg'

  im_io.seek(0)
  return send_file(im_io, mimetype=mimetype)

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=8080)