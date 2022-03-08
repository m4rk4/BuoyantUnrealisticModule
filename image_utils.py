import av, requests
from io import BytesIO
from PIL import Image, ImageDraw

import utils

import logging

logger = logging.getLogger(__name__)


def text(s):
    WIDTH = 3
    HEIGHT = 2
    PIXEL_SCALE = 200

    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, WIDTH * PIXEL_SCALE, HEIGHT * PIXEL_SCALE)
    ctx = cairo.Context(surface)
    ctx.scale(PIXEL_SCALE, PIXEL_SCALE)

    ctx.rectangle(0, 0, WIDTH, HEIGHT)
    ctx.set_source_rgb(0.8, 0.8, 1)
    ctx.fill()

    # Drawing code
    ctx.set_source_rgb(1, 0, 0)
    ctx.set_font_size(0.75)
    ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.move_to(0, 0.6)
    ctx.show_text("Outline")

    ctx.move_to(0, 1.2)
    ctx.text_path("Outline")
    ctx.set_line_width(0.02)
    ctx.stroke()
    # End of drawing code

    surface.write_to_png('text.png')


def resize(im, width, height, scale):
    if scale:
        h = (im.height * int(scale)) // 100
        w = (im.width * int(scale)) // 100
    elif width and height:
        w = int(width)
        h = int(height)
    elif width:
        w = int(width)
        h = (im.height * w) // im.width
    elif height:
        h = int(height)
        w = (im.width * h) // im.height
    else:
        return im
    return im.resize((w, h), resample=Image.LANCZOS)


def crop(im, crop_args):
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
    else:
        return im
    return im.crop((x, y, x + w, y + h))


def add_border(im, b, color):
    w = im.width
    h = im.height
    if len(color) == 4:
        new_im = Image.new("RGBA", (w + 2 * b, h + 2 * b), color)
    else:
        new_im = Image.new("RGB", (w + 2 * b, h + 2 * b), color)
    new_im.paste(im, (b, b))
    return new_im


def add_mask(im, type):
    # Credit to: https://stackoverflow.com/questions/890051/how-do-i-generate-circular-thumbnails-with-pil
    if type == 'circle':
        s = 3* min(im.width, im.height)
        mask_size = (s, s)
    elif type == 'ellipse':
        mask_size = (3 * im.width, 3 * im.height)
    else:
        logger.warning('unknown mask type ' + type)
        return False
    mask = Image.new('L', mask_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse([(0, 0), mask_size], fill=255)
    mask = mask.resize(im.size, Image.ANTIALIAS)
    im.putalpha(mask)
    return True


def add_overlay(im, overlay, args):
    im_overlay = None
    if overlay == 'video':
        overlays = [{"width": 512, "height": 360, "url": "./static/video_play_button-512x360.png"},
                    {"width": 384, "height": 270, "url": "./static/video_play_button-384x270.png"},
                    {"width": 256, "height": 180, "url": "./static/video_play_button-256x180.png"},
                    {"width": 192, "height": 135, "url": "./static/video_play_button-192x135.png"},
                    {"width": 128, "height": 90, "url": "./static/video_play_button-128x90.png"},
                    {"width": 97, "height": 68, "url": "./static/video_play_button-97x68.png"},
                    {"width": 64, "height": 45, "url": "./static/video_play_button-64x45.png"},
                    {"width": 48, "height": 34, "url": "./static/video_play_button-48x34.png"}]
        if im.height < im.width:
            overlay = utils.closest_dict(overlays, 'height', im.height // 5)
        else:
            overlay = utils.closest_dict(overlays, 'height', im.width // 5)
        im_overlay = Image.open(overlay['url'])

    elif overlay == 'audio':
        overlays = [{"width": 512, "height": 512, "url": "./static/play_button-512x512.png"},
                    {"width": 384, "height": 384, "url": "./static/play_button-384x384.png"},
                    {"width": 256, "height": 256, "url": "./static/play_button-256x256.png"},
                    {"width": 192, "height": 192, "url": "./static/play_button-192x192.png"},
                    {"width": 128, "height": 128, "url": "./static/play_button-128x128.png"},
                    {"width": 96, "height": 96, "url": "./static/play_button-96x96.png"},
                    {"width": 64, "height": 64, "url": "./static/play_button-64x64.png"},
                    {"width": 48, "height": 48, "url": "./static/play_button-48x48.png"},
                    {"width": 32, "height": 32, "url": "./static/play_button-32x32.png"}]
        if im.height < im.width:
            overlay = utils.closest_dict(overlays, 'height', im.height // 5)
        else:
            overlay = utils.closest_dict(overlays, 'height', im.width // 5)
        im_overlay = Image.open(overlay['url'])

    elif overlay.startswith('http'):
        r = requests.get(overlay)
        if r.status_code == 200:
            io_overlay = BytesIO(r.content)
            im_overlay = Image.open(io_overlay).convert("RGBA")
            im_overlay = resize(im_overlay, args.get('overlay_width'), args.get('overlay_height'), args.get('overlay_scale'))

    if im_overlay:
        # Default to center
        x = (im.width - im_overlay.width) // 2
        y = (im.height - im_overlay.height) // 2
        if args.get('overlay_position'):
            pos = tuple(map(str, args['overlay_position'][1:-1].split(',')))
            if len(pos) == 2:
                if pos[0]:
                    # Left
                    x = int(pos[0])
                    if x < 0:
                        # Relative to right
                        x = im.width - im_overlay.width + x
                if pos[1]:
                    # Top
                    y = int(pos[1])
                    if y < 0:
                        # Relative to bottom
                        y = im.height - im_overlay.height + y
        im.paste(im_overlay, (x, y), mask=im_overlay)
    else:
        logger.warning('unable to create overlay for ' + overlay)
        return False
    return True


def get_image(args):
    im = None
    im_io = None
    save = False
    resized = False

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
                im = Image.new('RGBA', (w, h), color=(0, 0, 0, 0))
                mimetype = 'image/png'
            else:
                im = Image.new('RGB', (w, h), color=color)
                mimetype = 'image/jpg'
        else:
            return None, 'No url given'

    if not im:
        try:
            if args['url'].endswith('mp4'):
                container = av.open(args['url'])
                for frame in container.decode(video=0):
                    im = frame.to_image()
                    break
                save = True
            else:
                r = requests.get(args['url'])
                if r.status_code == 200:
                    im_io = BytesIO(r.content)
                    im = Image.open(im_io)
                    mimetype = im.get_format_mimetype()
        except Exception as e:
            logger.warning('image exception: ' + str(e))
            im = None

    if not im:
        return None, 'Something went wrong :('

    if im.mode == 'P':
        im = im.convert('RGBA')

    # Do operations in the order of the args
    for arg, val in args.items():
        if (arg == 'height' or arg == 'width' or arg == 'scale') and resized == False:
            im = resize(im, args.get('width'), args.get('height'), args.get('scale'))
            resized = True
            save = True

        elif arg == 'crop':
            im = crop(im, args['crop'].split(','))
            save = True

        elif arg == 'overlay':
            if add_overlay(im, val, args):
                save = True

        elif arg == 'mask':
            if add_mask(im, val):
                mimetype = 'image/png'
                save = True

        elif arg == 'border':
            if args.get('color'):
                color = tuple(map(int, args['color'][1:-1].split(',')))
            else:
                color = (0, 0, 0, 0)
            if len(color) < 3:
                color = (0, 0, 0)
            elif len(color) > 4:
                color = (0, 0, 0)
            im = add_border(im, int(val), color)
            mimetype = 'image/png'
            save = True

    if save:
        im_io = BytesIO()
        if im.mode in ['RGBA', 'P', 'LA']:
            im.save(im_io, 'PNG')
            mimetype = 'image/png'
        else:
            im.save(im_io, 'JPEG')
            mimetype = 'image/jpeg'

    im_io.seek(0)
    return im_io, mimetype
