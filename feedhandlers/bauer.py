import json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from markdown2 import markdown
from urllib.parse import parse_qs, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(image, width=1000):
    w = min(width, image['width'])
    return 'https://images.bauerhosting.com/{}/{}?auth=format&q=80&w={}'.format(image['path'], image['fileName'], w)


def add_image(image_meta, width=1000):
    img_src = resize_image(image_meta['image'])
    captions = []
    if image_meta.get('caption'):
        captions.append(image_meta['caption'])
    if image_meta.get('credits'):
        captions.append(image_meta['credits'])
    desc = ''
    if image_meta.get('titleText'):
        desc += '<h3>' + image_meta['titleText'] + '</h3>'
    if image_meta.get('description'):
        desc += add_content_text(image_meta['description'])
    return utils.add_image(img_src, ' | '.join(captions), desc=desc)


def add_content_text(content_text):
    # fix links
    text = re.sub(r'\{#[^\}]+\}', '', content_text)
    text = re.sub(r':a\[(.*?)\]\{.*?href=\'([^\']+)\'.*?\}', r'[\1](\2)', text)
    return markdown(text)


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
    next_url = 'https://assets.onebauer.media/_next/data/{}/{}{}'.format(site_json['buildId'], site_json['site'], path)
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
    # Bauer Media brands: https://www.bauermedia.co.uk/brands/
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.json')

    if next_data['pageProps']['template'] == 'article':
        article_json = next_data['pageProps']['queryData']['getArticleByFurl']
    elif next_data['pageProps']['template'] == 'review':
        article_json = next_data['pageProps']['queryData']['getReviewByFurl']
    else:
        logger.warning('unhandled page template {} in {}'.format(next_data['pageProps']['template'], url))
        return None

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['title']

    tz_loc = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromtimestamp(article_json['publicationDate'] / 1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_loc = datetime.fromtimestamp(article_json['lastModifiedAt'] / 1000)
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if article_json.get('author'):
        item['author']['name'] = article_json['author']['fullname']
    elif article_json.get('author_custom'):
        authors = [it.strip() for it in article_json['author_custom'].split(',')]
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = urlsplit(item['url']).netloc

    item['tags'] = []
    for it in article_json['categories']:
        if it.get('parent'):
            item['tags'].append(it['parent']['name'])
        item['tags'].append(it['name'])
    if article_json.get('film'):
        for it in article_json['film']:
            item['tags'].append(it['title'])
    if article_json.get('people'):
        for it in article_json['people']:
            item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''

    if article_json.get('nutshell'):
        item['summary'] = article_json['nutshell']
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['nutshell'])
    elif article_json.get('excerpt'):
        if not article_json['excerpt'].endswith('...'):
            item['summary'] = article_json['excerpt']
            item['content_html'] += '<p><em>{}</em></p>'.format(article_json['excerpt'])

    if article_json.get('heroImage'):
        item['_image'] = resize_image(article_json['heroImage'][0]['image'])
        item['content_html'] += add_image(article_json['heroImage'][0])

    if article_json.get('rating'):
        text = ''
        n = int(article_json['rating'])
        for i in range(5):
            if i < n:
                text += '★'
            else:
                text += '☆'
        if n == 5:
            item['content_html'] += '<div>&nbsp;</div><div style="font-size:2em; font-weight:bold; color:red; text-align:center;">{}</div>'.format(text)
        else:
            item['content_html'] += '<div>&nbsp;</div><div style="font-size:2em; font-weight:bold; text-align:center;">{}</div>'.format(text)

    if article_json.get('verdict'):
        item['content_html'] += '<div><b>{}</b></div>'.format(article_json['verdict'])

    for layout_item in article_json['_layout']:
        if layout_item['type'] == 'content':
            item['content_html'] += add_content_text(layout_item['content']['text'])
        elif layout_item['type'] == 'pullQuotes':
            m = re.search(r'^>([^>]+)', layout_item['content']['text'])
            if m:
                text = m.group(1)
                m = re.search(r'>\s+>(.*)', layout_item['content']['text'])
                if m:
                    cite = m.group(1)
                else:
                    cite = ''
                item['content_html'] += utils.add_pullquote(text, cite)
            else:
                logger.warning('unhandled pullquote in ' + item['url'])
        elif layout_item['type'] == 'images':
            item['content_html'] += add_image(layout_item['content'])
        elif layout_item['type'] == 'imageGalleries':
            for image in layout_item['content']['images']:
                item['content_html'] += add_image(image)
        elif layout_item['type'] == 'embeds':
            if layout_item['content'].get('url'):
                item['content_html'] += utils.add_embed(layout_item['content']['url'])
            else:
                logger.warning('unhandled layout embed provider {} in {}'.format(layout_item['content']['provider'], item['url']))
        elif layout_item['type'] == 'htmlInsert':
            if layout_item['content']['text'].strip().startswith('<iframe'):
                m = re.search(r'src="([^"]+)"', layout_item['content']['text'])
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled layout htmlInsert in ' + item['url'])
        elif layout_item['type'] == 'products':
            item['content_html'] += '<div style="margin:1em;"><div style="font-size:1.1em; font-weight:bold; border-bottom:1px solid black;"><a href="{}">{}</a></div><div>&nbsp;</div>'.format(layout_item['content']['actionLink'], layout_item['content']['title'])
            item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:1em; align-items:center;">'
            item['content_html'] += '<div style="flex:1; min-width:256px;"><a href="{}"><img src="{}" style="width:100%;"/></a></div>'.format(layout_item['content']['actionLink'], resize_image(layout_item['content']['images'][0]['image']))
            # TODO: price assumes GBP
            item['content_html'] += '<div style="flex:1; min-width:256px; text-align:center;"><div style="font-size:1.1em;">Price: <span style="color:red;">£{}</span></div>'.format(layout_item['content']['price'])
            item['content_html'] += '<div style="font-size:0.9em;"><a href="{}">{}</a></div>'.format(layout_item['content']['actionLink'], urlsplit(layout_item['content']['actionLink']).netloc)
            if layout_item['content']['actionText'] == 'viewoffer':
                text = 'View Offer'
            else:
                text = layout_item['content']['actionText']
            item['content_html'] += '<div style="margin:8px 0 8px 0;"><a href="{}"><span style="display:inline-block; min-width:180px; text-align: center; padding:0.5em; font-size:0.8em; text-transform:uppercase; border:1px solid rgb(5, 125, 188);">{} ➞</span></a></div>'.format(
                layout_item['content']['actionLink'], text)
            item['content_html'] += '</div></div>'
            if layout_item['content'].get('description'):
                item['content_html'] += '<div><b>Description</b></div>' + add_content_text(layout_item['content']['description'])
            item['content_html'] += '</div>'
        else:
            logger.warning('unhandled layout type {} in {}'.format(layout_item['type'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://rss.onebauer.media/api/feed-aggregator?hostname=https://www.empireonline.com
    split_url = urlsplit(url)
    params = parse_qs(split_url.query)
    if params.get('hostname'):
        rss_site = utils.get_site_json(params['hostname'][0])
        if rss_site:
            return rss.get_feed(url, args, rss_site, save_debug, get_content)
    logger.warning('unsupported feed url ' + url)
    return None
