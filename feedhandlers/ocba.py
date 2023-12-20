import re
from bs4 import BeautifulSoup

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug):
    item = wp_posts.get_content(url, args, site_json, save_debug)

    def vc_entity(matchobj):
        if matchobj.group(1).startswith('column') or matchobj.group(1).startswith('row'):
            return ''
        elif matchobj.group(1) == 'single_image':
            # print(matchobj.group(0))
            m = re.search(r'image=”(\d+)″', matchobj.group(0))
            if m:
                media_json = utils.get_url_json('https://ohiocraftbeer.org/wp-json/wp/v2/media/' + m.group(1))
                if media_json:
                    img_src = media_json['source_url']
                    captions = []
                    if media_json.get('description'):
                        soup = BeautifulSoup(media_json['description']['rendered'], 'html.parser')
                        caption = soup.get_text().strip()
                        if caption:
                            captions.append(caption)
                    if media_json.get('caption'):
                        caption = re.sub('^<p>(.*)</p>$', r'\1', media_json['caption']['rendered'])
                        caption = caption.strip()
                        if caption:
                            captions.append(caption)
                    caption = ' | '.join(captions)
                    m = re.search(r'link=”([^”]+)”', matchobj.group(0))
                    if m:
                        link = m.group(1)
                    else:
                        link = ''
                    return utils.add_image(img_src, caption, link=link)
        else:
            logger.warning('unhandled vc entity ' + matchobj.group(1))
            return ''
    item['content_html'] = re.sub(r'\[/?vc_(\w+)[^\]]*\]', vc_entity, item['content_html'])

    item['content_html'] = re.sub(r'<(/?)h6>', r'<\1h3>', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
