import json, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(image, width=1200):
    if image.get('cdn'):
        sizes = []
        for size in image['cdn']['sizes']:
            if not re.search(r'cTC|cMC', size, flags=re.I):
                m = re.search(r'^(\d+)x', size)
                if m:
                    s = {"width": int(m.group(1)), "size": size}
                    sizes.append(s)
        size = utils.closest_dict(sizes, 'width', width)
        img_src = 'https://{}/{}/{}'.format(image['cdn']['host'], size['size'], image['cdn']['fileName'])
    else:
        size = image['url'].split('/')[-2]
        img_src = image['url'].replace(size, '{}x'.format(width))
    return img_src


def add_image(image):
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    if image.get('photoCredit'):
        captions.append(image['photoCredit'])
    return utils.add_image(resize_image(image), ' | '.join(captions))


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if split_url.netloc == 'newsinteractive.post-gazette.com':
        wp_site_json = {
            "module": "wp_posts",
            "posts_path": "/wp/v2/posts",
        }
        if 'photos' in paths:
            wp_site_json['wpjson_path'] = "https://newsinteractive.post-gazette.com/photos/wp-json"
        else:
            wp_site_json['wpjson_path'] = "https://newsinteractive.post-gazette.com/wp-json"
        args['skip_lede_img'] = True
        return wp_posts.get_content(url, args, wp_site_json, save_debug)

    api_url = site_json['api_base_url'] + '/top/2/article/' + paths[-1] + '/'
    api_json = utils.get_url_json(api_url, site_json=site_json)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    article = api_json['articles'][0]
    item = {}
    item['id'] = article['storyID']
    item['url'] = article['link']
    item['title'] = article['title']

    # dt = datetime.strptime(article['pubDate'], '%a, %d %b %Y %H:%M:%S %z').astimezone(timezone.utc)
    dt = dateutil.parser.parse(article['pubDate']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    # dt = datetime.strptime(article['contentModified'], '%a, %d %b %Y %H:%M:%S %z').astimezone(timezone.utc)
    if article.get('contentModified'):
        dt = dateutil.parser.parse(article['contentModified']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()
    elif article.get('displayUpdateDate'):
        dt = dateutil.parser.parse(article['displayUpdateDate']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": re.sub(r'^By ', '', article['author'])
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if isinstance(article['images'], list):
        article_images = article['images'].copy()
    elif isinstance(article['images'], dict):
        article_images = []
        for i in range(len(article['images'])):
            article_images.append(article['images'][str(i)])

    item['image'] = resize_image(article_images[0])
    item['content_html'] = add_image(article_images[0])
    n_img = 1

    soup = BeautifulSoup(article['body'], 'html.parser')

    for el in soup.find_all(class_='pg-embedcode-largeimage'):
        new_html = ''
        title = el.img['src'].split('/')[-1].lower()
        for i, image in enumerate(article_images):
            if title in image['url']:
                new_html = add_image(image)
                n_img += 1
                break
        if not new_html:
            captions = []
            it = el.find(class_='pg-embedcode-largeimage-text')
            if it:
                caption = it.get_text().strip()
                if caption:
                    captions.append(caption)
            it = el.find(class_='pg-embedcode-largeimage-credit')
            if it:
                caption = it.get_text().strip()
                if caption:
                    captions.append(caption)
            new_html = utils.add_image(el.img['src'], ' | '.join(captions))
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('blockquote'):
        new_html = ''
        if el.get('class'):
            if 'twitter-tweet' in el['class']:
                links = el.find_all('a')
                new_html = utils.add_embed(links[-1]['href'])
            elif 'instagram-media' in el['class']:
                new_html = utils.add_embed(el['data-instgrm-permalink'])
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled blockquote in ' + item['url'])

    for el in soup.find_all(attrs={"data-ps-embed-type": "slideshow"}):
        slideshow_html = utils.get_url_html('https://post-gazette.photoshelter.com/embed?type=slideshow&G_ID=' + el['data-ps-embed-gid'])
        m = re.search(r'"api_key":"(\w+)"', slideshow_html)
        if m:
            post_data = {
                "fields": "*",
                "f_https_link": "t",
                "api_key": m.group(1)
            }
            slideshow_json = utils.post_url('https://post-gazette.photoshelter.com/psapi/v2.0/gallery/' + el['data-ps-embed-gid'], data=post_data)
            if slideshow_json:
                post_data = {
                    "fields": "*",
                    "f_https_link": "t",
                    "page": 1,
                    "ppg": 250,
                    "limit": 250,
                    "offset": 0,
                    "api_key": m.group(1)
                }
                images_json = utils.post_url('https://post-gazette.photoshelter.com/psapi/v2.0/gallery/{}/images'.format(el['data-ps-embed-gid']), data=post_data)
                if images_json:
                    new_html = '<h3>Gallery: {} ({} images)</h3>'.format(slideshow_json['data']['name'], len(images_json['data']['images']))
                    for image in images_json['data']['images']:
                        img_src = '{}/sec={}/fit=1000x800'.format(image['link_elements']['base'], image['link_elements']['token'])
                        caption = image['caption'].replace('#standalone', '').strip()
                        new_html += utils.add_image(img_src, caption) + '<br/>'
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
                    el.decompose()

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        it = el
        while it.parent and (it.parent.name == 'p' or it.parent.name == 'div'):
            it = it.parent
        it.insert_after(new_el)
        it.decompose()

    for el in soup.find_all('script'):
        el.decompose()

    item['content_html'] += str(soup)
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(div|figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])

    if len(article_images) > n_img:
        gallery_images = []
        gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
        for i, image in enumerate(article_images):
            img_src = resize_image(image, 1800)
            thumb = resize_image(image, 800)
            captions = []
            if image.get('caption'):
                captions.append(image['caption'])
            if image.get('photoCredit'):
                captions.append(image['photoCredit'])
            caption = ' | '.join(captions)
            gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
            gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
        if i % 2 == 0:
            gallery_html += '<div style="flex:1; min-width:360px;">&nbsp;</div>'
        gallery_html += '</div>'
        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
        item['content_html'] += '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + gallery_html

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)