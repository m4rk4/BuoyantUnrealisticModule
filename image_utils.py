import asyncio, av, cloudscraper, curl_cffi, math, re
from io import BytesIO
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageOps
from playwright.async_api import async_playwright
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def resize(im, width, height, scale):
    if scale:
        h = math.ceil((im.height * float(scale)) / 100)
        w = math.ceil((im.width * float(scale)) / 100)
    elif width and height:
        w = int(width)
        h = int(height)
    elif width:
        w = int(width)
        h = math.ceil((im.height * w) / im.width)
    elif height:
        h = int(height)
        w = math.ceil((im.width * h) / im.height)
    else:
        return im
    return im.resize((w, h), resample=Image.LANCZOS)


def crop_bbox(im, invert):
    # Removes surrounding black borders
    if isinstance(invert, str) and invert == '1':
        # invert to remove white borders
        bbox = ImageOps.invert(im.convert("RGB")).getbbox()
    else:
        bbox = im.getbbox()
    return im.crop(bbox)


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
        v = int(crop_args[0])
        # Centered square
        if v == 0:
            w = min(im.width, im.height)
        elif v <= im.width and v <= im.height:
            w = v
        else:
            w = min(v, im.width, im.height)
        h = w
        x = (im.width - w) // 2
        y = (im.height - h) // 2
    elif len(crop_args) == 0:
        im_box = im.getbox()
        return im.crop(im_box)
    else:
        return im
    return im.crop((x, y, x + w, y + h))


def add_border(im, border, color):
    if border.isnumeric():
        bx = int(border)
        by = int(border)
    else:
        try:
            b = tuple(map(int, border[1:-1].split(',')))
            bx = b[0]
            by = b[1]
        except:
            logger.warning('border should be specified as an integer or integer pair (x,y)')
            return im
    w = im.width
    h = im.height
    if len(color) == 4:
        new_im = Image.new("RGBA", (w + 2 * bx, h + 2 * by), color)
    else:
        new_im = Image.new("RGB", (w + 2 * bx, h + 2 * by), color)
    new_im.paste(im, (bx, by))
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
    mask = mask.resize(im.size, Image.Resampling.LANCZOS)
    im.putalpha(mask)
    return True


def add_overlay(im, overlay, args):
    im_overlay = None
    if overlay == 'video':
        overlays = [
            {"width": 512, "height": 360, "url": "./static/video_play_button-512x360.png"},
            {"width": 384, "height": 270, "url": "./static/video_play_button-384x270.png"},
            {"width": 256, "height": 180, "url": "./static/video_play_button-256x180.png"},
            {"width": 192, "height": 135, "url": "./static/video_play_button-192x135.png"},
            {"width": 128, "height": 90, "url": "./static/video_play_button-128x90.png"},
            {"width": 97, "height": 68, "url": "./static/video_play_button-97x68.png"},
            {"width": 64, "height": 45, "url": "./static/video_play_button-64x45.png"},
            {"width": 48, "height": 34, "url": "./static/video_play_button-48x34.png"}
        ]
        if im.height < im.width:
            overlay = utils.closest_dict(overlays, 'height', im.height // 5)
        else:
            overlay = utils.closest_dict(overlays, 'height', im.width // 5)
        im_overlay = Image.open(overlay['url'])

    elif overlay == 'audio':
        overlays = [
            {"width": 512, "height": 512, "url": "./static/play_button-512x512.png"},
            {"width": 384, "height": 384, "url": "./static/play_button-384x384.png"},
            {"width": 256, "height": 256, "url": "./static/play_button-256x256.png"},
            {"width": 192, "height": 192, "url": "./static/play_button-192x192.png"},
            {"width": 128, "height": 128, "url": "./static/play_button-128x128.png"},
            {"width": 96, "height": 96, "url": "./static/play_button-96x96.png"},
            {"width": 64, "height": 64, "url": "./static/play_button-64x64.png"},
            {"width": 48, "height": 48, "url": "./static/play_button-48x48.png"},
            {"width": 32, "height": 32, "url": "./static/play_button-32x32.png"}
        ]
        if im.height < im.width:
            overlay = utils.closest_dict(overlays, 'height', im.height // 3, greater_than=True)
        else:
            overlay = utils.closest_dict(overlays, 'height', im.width // 3, greater_than=True)
        im_overlay = Image.open(overlay['url'])

    elif overlay == 'gallery':
        overlays = [
            {"width": 512, "height": 512, "url": "./static/gallery_button-512x512.png"},
            {"width": 256, "height": 256, "url": "./static/gallery_button-256x256.png"},
            {"width": 128, "height": 128, "url": "./static/gallery_button-128x128.png"},
            {"width": 64, "height": 64, "url": "./static/gallery_button-64x64.png"},
            {"width": 32, "height": 32, "url": "./static/gallery_button-32x32.png"}
        ]
        if im.height < im.width:
            overlay = utils.closest_dict(overlays, 'height', im.height // 3, greater_than=True)
        else:
            overlay = utils.closest_dict(overlays, 'height', im.width // 3, greater_than=True)
        im_overlay = Image.open(overlay['url'])

    elif overlay.startswith('http'):
        im_io = read_image(overlay)
        if im_io:
            im_overlay = Image.open(im_io)
            im_overlay = im_overlay.convert("RGBA")
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
            browser_name = config.default_browser

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
        elif browser_name == 'edge':
            engine = playwright.chromium
            if not device:
                device = playwright.devices['Desktop Edge']
        else:
            engine = playwright.chromium
            if not device:
                device = playwright.devices['Desktop Chrome']

        if 'headed' in args:
            headless = False
        else:
            headless = True

        if browser_name == 'edge':
            browser = await engine.launch(channel="msedge", headless=headless)
        else:
            browser = await engine.launch(headless=headless)

        if device:
            context = await browser.new_context(**device)
            page = await context.new_page()
        else:
            context = None
            page = await browser.new_page()

        if 'viewport' in args:
            m = re.search(r'(\d+),(\d+)', args['viewport'])
            if m:
                await page.set_viewport_size({"width": int(m.group(1)), "height": int(m.group(2))})

        if 'wait_until' in args:
            await page.goto(url, wait_until=args['wait_until'])
        else:
            await page.goto(url)

        if 'waitfor' in args:
            await page.wait_for_selector(args['waitfor'])

        if 'waitfortime' in args:
            # time in ms
            await page.wait_for_timeout(int(args['waitfortime']))

        await page.keyboard.press('Escape')

        if 'locator' in args:
            ss = await page.locator(args['locator']).screenshot()
        else:
            ss = await page.screenshot()

        if not ss:
            if device:
                await context.close()
            await browser.close()
            return None

        im_io = BytesIO()
        im_io.write(ss)
        im_io.seek(0)

        if context:
            await context.close()
        await browser.close()
    return im_io


def read_image(img_src):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "accept-language": "en-US,en;q=0.9,de;q=0.8",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"107\", \"Chromium\";v=\"107\", \"Not=A?Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36 Edg/107.0.1418.35"
    }
    if 'preview.redd.it' in img_src:
        # headers['accept'] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        r = curl_cffi.get(img_src, impersonate="chrome", headers={"accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"}, proxies=config.proxies)
    elif 'truthsocial.com' in img_src:
        print(img_src)
        # scraper = cloudscraper.create_scraper()
        # r = scraper.get(img_src)
        r = curl_cffi.get(img_src, impersonate="chrome")
    else:
        r = curl_cffi.get(img_src, impersonate="chrome", proxies=config.proxies)
    if r.status_code != 200:
        logger.warning('status code {} getting {}'.format(r.status_code, img_src))
        return None
    else:
        img_content = r.content

    # if 'www.cbc.ca' in img_src:
    #     img_content = utils.get_url_content(img_src, headers=headers, use_proxy=True, use_curl_cffi=True)
    # else:
    #     img_content = utils.get_url_content(img_src, headers=headers)

    # im = None
    if img_content:
        im_io = BytesIO(img_content)
        # im = Image.open(im_io)
    return im_io


def get_image(args, im=None, im_io=None):
    img_args = args.copy()
    save = False
    resized = False
    mimetype = ''

    if im_io:
        im = Image.open(im_io)
    elif not im:
        if 'url' in img_args:
            container = None
            img_src = img_args['url']
            while img_src:
                container = None
                try:
                    container = av.open(img_src)
                except av.error.InvalidDataError:
                    im_io = read_image(img_src)
                    if im_io:
                        container = av.open(im_io)
                if container:
                    try:
                        if re.search(r'dash|hls|mp4|m4a|mov|mpeg|webm', container.format.name):
                            stream = container.streams.video[0]
                            stream.codec_context.skip_frame = "NONKEY"
                            for frame in container.decode(stream):
                                if frame.width > frame.height:
                                    w = 1280
                                    h = int(frame.height * w / frame.width)
                                else:
                                    h = 800
                                    w = int(frame.width * h / frame.height)
                                im = frame.reformat(width=w, height=h).to_image()
                                # im = frame.to_image()
                                break
                            save = True
                        elif re.search(r'image|jpeg|png|webp', container.format.name):
                            if not im_io:
                                im_io = read_image(img_src)
                            if im_io:
                                im = Image.open(im_io)
                                mimetype = im.get_format_mimetype()
                        img_src = ''
                    except av.HTTPForbiddenError:
                        if '/proxy/' not in img_src:
                            img_src = config.server + '/proxy/' + img_args['url']
                        else:
                            img_src = ''
                    except av.error.InvalidDataError:
                        if re.search(r'\.(mp4|m4a|mov|mpeg|webm)', img_args['url']):
                            loop = asyncio.ProactorEventLoop()
                            asyncio.set_event_loop(loop)
                            im_io = loop.run_until_complete(get_screenshot(img_args['url'], img_args))
                            if im_io:
                                im = Image.open(im_io)
                                img_args['cropbbox'] = '0'
                        img_src = ''
                    except Exception as e:
                        logger.warning('image exception: ' + str(e))
                        img_src = ''
                    if container:
                        container.close()

    if not im:
        if 'url' in img_args and re.search(r'\.(mp4|m4a|mov|mpeg|webm)', img_args['url']):
            im = Image.new('RGB', (1280, 720), color='SlateGray')
            mimetype = 'image/jpg'
        else:
            if 'width' in img_args:
                w = int(img_args['width'])
            else:
                w = -1
            if 'height' in img_args:
                h = int(img_args['height'])
            else:
                h = -1
            if w > 0 and h < 0:
                h = w
            elif w < 0 and h > 0:
                w = h
            if w > 0 and h > 0:
                if 'color' in img_args:
                    if img_args['color'].count(',') == 0:
                        color = img_args['color']
                    else:
                        r, g, b = img_args['color'].split(',')
                        color = (int(r), int(g), int(b))
                else:
                    color = 'SlateGray'
                if color == 'none':
                    im = Image.new('RGBA', (w, h), color=(0, 0, 0, 0))
                    mimetype = 'image/png'
                else:
                    im = Image.new('RGB', (w, h), color=color)
                    mimetype = 'image/jpg'

    if not im:
        return None, 'Something went wrong :('

    if im.mode == 'P':
        im = im.convert('RGBA')

    # Do operations in the order of the args
    for arg, val in img_args.items():
        if arg == 'letterbox':
            try:
                b = tuple(map(int, args['letterbox'][1:-1].split(',')))
                w = b[0]
                h = b[1]
            except:
                logger.warning('letterbox should be specified as an integer pair (w,h)')
                w = -1
                h = -1
            if w > 0 and h > 0:
                scale = min(w / im.width, h / im.height) * 100
                im = resize(im, '', '', scale)
                if args.get('color'):
                    if args['color'].startswith('#'):
                        color = ImageColor.getcolor(args['color'], 'RGB')
                    else:
                        try:
                            color = tuple(map(int, args['color'][1:-1].split(',')))
                        except:
                            logger.warning('invalid color ' + args['color'])
                            color = (0, 0, 0, 0)
                else:
                    color = (0, 0, 0, 0)
                if len(color) < 3:
                    color = (0, 0, 0)
                elif len(color) > 4:
                    color = (0, 0, 0)
                border = '({},{})'.format(math.ceil((w - im.width) / 2), math.ceil((h - im.height) / 2))
                im = add_border(im, border, color)
                mimetype = 'image/png'
                resized = True
                save = True
        elif (arg == 'height' or arg == 'width' or arg == 'scale') and resized == False:
            im = resize(im, img_args.get('width'), img_args.get('height'), img_args.get('scale'))
            resized = True
            save = True

        elif arg == 'crop':
            im = crop(im, img_args['crop'].split(','))
            save = True

        elif arg == 'cropbbox':
            im = crop_bbox(im, img_args['cropbbox'])
            save = True

        elif arg == 'overlay':
            if add_overlay(im, val, img_args):
                save = True

        elif arg == 'mask':
            if add_mask(im, val):
                mimetype = 'image/png'
                save = True

        elif arg == 'border':
            if img_args.get('color'):
                if img_args['color'].startswith('#'):
                    color = ImageColor.getcolor(img_args['color'], 'RGB')
                else:
                    try:
                        color = tuple(map(int, img_args['color'][1:-1].split(',')))
                    except:
                        logger.warning('invalid color ' + img_args['color'])
                        color = (0, 0, 0, 0)
            else:
                color = (0, 0, 0, 0)
            if len(color) < 3:
                color = (0, 0, 0)
            elif len(color) > 4:
                color = (0, 0, 0)
            im = add_border(im, val, color)
            mimetype = 'image/png'
            save = True

        elif arg == 'rotate':
            im = im.rotate(int(val), Image.NEAREST, expand=1)
            save = True

        elif arg == 'blur':
            im = im.filter(ImageFilter.BLUR)
            save = True

    if save:
        im_io = BytesIO()
        # print(im.mode)
        if im.mode in ['RGBA', 'P', 'LA']:
            im.save(im_io, 'PNG')
            mimetype = 'image/png'
        else:
            im.save(im_io, 'JPEG')
            mimetype = 'image/jpeg'

    im_io.seek(0)
    return im_io, mimetype


# def text(s):
#     WIDTH = 3
#     HEIGHT = 2
#     PIXEL_SCALE = 200
#
#     surface = cairo.ImageSurface(cairo.FORMAT_RGB24, WIDTH * PIXEL_SCALE, HEIGHT * PIXEL_SCALE)
#     ctx = cairo.Context(surface)
#     ctx.scale(PIXEL_SCALE, PIXEL_SCALE)
#
#     ctx.rectangle(0, 0, WIDTH, HEIGHT)
#     ctx.set_source_rgb(0.8, 0.8, 1)
#     ctx.fill()
#
#     # Drawing code
#     ctx.set_source_rgb(1, 0, 0)
#     ctx.set_font_size(0.75)
#     ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
#     ctx.move_to(0, 0.6)
#     ctx.show_text("Outline")
#
#     ctx.move_to(0, 1.2)
#     ctx.text_path("Outline")
#     ctx.set_line_width(0.02)
#     ctx.stroke()
#     # End of drawing code
#
#     surface.write_to_png('text.png')
