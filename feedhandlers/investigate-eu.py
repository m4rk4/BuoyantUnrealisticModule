import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import wp_posts

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    return 'https://www.investigate-europe.eu/_next/image?url={}&w={}&q=75'.format(quote_plus(img_src), width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
    path += '.json'
    if 'posts' in paths:
        params = '?slug=' + paths[-1]
    else:
        params = ''
    next_url = '{}://{}/_next/data/{}/{}{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], site_json['lang'], path, params)
    # print(next_url)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find __NEXT_DATA__ in ' + url)
            return None
        next_data = json.loads(el.string)
        if next_data['buildId'] != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = next_data['buildId']
            utils.update_sites(url, site_json)
        return next_data['props']
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/debug.json')
    if next_data['pageProps'].get('post'):
        post_json = next_data['pageProps']['post']
    elif next_data['pageProps'].get('mediaStory'):
        post_json = next_data['pageProps']['mediaStory']
    else:
        logger.warning('unknown post data for ' + url)
        return None

    item = {}
    if post_json.get('id'):
        item['id'] = post_json['id']
    else:
        item['id'] = post_json['slug']

    item['url'] = url
    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['publishDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    authors = [it['value']['name'] for it in post_json['author']]
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if post_json.get('investigation'):
        item['tags'] = []
        item['tags'].append(post_json['investigation']['value']['title'])
        if post_json['investigation']['value'].get('theme'):
            item['tags'].append(post_json['investigation']['value']['theme']['value']['title'])

    if post_json['meta'].get('description'):
        item['summary'] = post_json['meta']['description']

    item['content_html'] = ''
    if post_json.get('lede'):
        item['content_html'] += '<p><em>' + post_json['lede'] + '</em></p>'

    if post_json.get('featuredVideo'):
        item['content_html'] += utils.add_embed(post_json['featuredVideo'])

    if post_json.get('featuredImage'):
        item['_image'] = resize_image(post_json['featuredImage']['url'])
        if not post_json.get('featuredVideo'):
            item['content_html'] += utils.add_image(item['_image'], post_json['featuredImage'].get('imageCredits'))

    if post_json.get('investigation'):
        item['tags'] = []
        item['tags'].append(post_json['investigation']['value']['title'])
        item['content_html'] += utils.add_blockquote('<div style="font-size:1.1em; font-weight:bold;">{}</div><p>{}</p>'.format(post_json['investigation']['value']['title'], post_json['investigation']['value']['aboutInvestigation']))
        if post_json['investigation']['value'].get('theme'):
            item['tags'].append(post_json['investigation']['value']['theme']['value']['title'])

    def format_children(children):
        content_html = ''
        for child in children:
            if child.get('type') and child['type'] == 'link':
                content_html += '<a href="' + child['url'] + '">' + format_children(child['children']) + '</a>'
            elif 'text' in child:
                if len(child['text']) > 0 and child['text'] != '\u00a0':
                    content_html += child['text']
            else:
                logger.warning('unhandled child {}'.format(child))
        return content_html

    for content in post_json['content']:
        if content['blockType'] == 'text-block':
            for block in content['textBlock']:
                item['content_html'] += '<p>' + format_children(block['children']) + '</p>'
        elif content['blockType'] == 'image-block':
            captions = []
            if content.get('Caption'):
                captions.append(content['Caption'])
            if content['image'].get('imageCredits'):
                captions.append(content['image']['imageCredits'])
            item['content_html'] += utils.add_image(resize_image(content['image']['url']), ' | '.join(captions))
        elif content['blockType'] == 'gallery-block':
            gallery_images = []
            gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
            for it in content['imageGallery']:
                img_src = resize_image(it['multiImagePlacement']['url'], 640)
                if it.get('Caption'):
                    caption = it['Caption']
                else:
                    caption = ''
                gallery_images.append({"src": it['multiImagePlacement']['url'], "caption": caption, "thumb": img_src})
                gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(img_src, caption, link=it['multiImagePlacement']['url']) + '</div>'
            gallery_html += '</div>'
            gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
            item['content_html'] += '<h3><a href="{}">View photo gallery</a></h3>'.format(gallery_url) + gallery_html
        elif content['blockType'] == 'video-block' and content.get('youtubeLink'):
            item['content_html'] += utils.add_embed(content['youtubeLink'])
        elif content['blockType'] == 'embed-block' and content['embedLink'].startswith('<iframe'):
            m = re.search(r'src=[\'"]([^\'"]+)[\'"]', content['embedLink'])
            item['content_html'] += utils.add_embed(m.group(1))
        elif content['blockType'] == 'quote-block':
            item['content_html'] += utils.add_pullquote(content['quote'], content['author'])
        elif content['blockType'] == 'fact-block':
            item['content_html'] += utils.add_blockquote(
                '<div style="font-size:1.1em; font-weight:bold;">{}</div><p>{}</p>'.format(content['title'], content['fact']))
        elif content['blockType'] == 'mig-embed-block':
            soup = BeautifulSoup(content['embedLink'], 'html.parser')
            item['content_html'] += wp_posts.format_content(soup.body.decode_contents(), item)
        else:
            logger.warning('unhandled content blockType {} in {}'.format(content['blockType'], item['url']))

    return item


def get_feed(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/feed.json')
