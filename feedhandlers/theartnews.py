import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(asset_id, width=1200):
    id = asset_id.split('-')
    return 'https://cdn.sanity.io/images/cxgd3urn/production/{}-{}.{}?w={}&auto=format'.format(id[1], id[2], id[3], width)


def get_next_data(url, site_json):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index.json'
    else:
        if split_url.path.endswith('/'):
            path = split_url.path[:-1]
        else:
            path = split_url.path
        path += '.json'

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
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


def render_content(contents, marks=None):
    content_html = ''
    for content in contents:
        if content['_type'] == 'block' and content.get('children'):
            if content['style'] == 'normal':
                content_html += '<p>' + render_content(content['children'], content['markDefs']) + '</p>'
            else:
                content_html += '<{0}>{1}</{0}>'.format(content['style'], render_content(content['children'], content['markDefs']))
        elif content['_type'] == 'span':
            start_tag = ''
            end_tag = ''
            if content.get('marks'):
                for it in content['marks']:
                    mark = None
                    if marks:
                        mark = next((x for x in marks if x['_key'] == it), None)
                    if mark:
                        if mark['_type'] == 'link':
                            start_tag += '<a href="{}">'.format(mark['href'])
                            end_tag = '</a>' + end_tag
                        elif mark['_type'] == 'internalLink':
                            start_tag += '<a href="https://www.theartnewspaper.com/{}">'.format(mark['href'])
                            end_tag = '</a>' + end_tag
                        else:
                            logger.warning('unhandled mark type ' + mark['_type'])
                    else:
                        start_tag += '<{}>'.format(it)
                        end_tag = '</{}>'.format(it) + end_tag
            content_html += start_tag + content['text'] + end_tag
        elif content['_type'] == 'image':
            img_src = resize_image(content['asset']['_id'])
            if content.get('caption'):
                caption = render_content(content['caption'][0]['children'])
            else:
                caption = ''
            content_html += utils.add_image(img_src, caption)
        elif content['_type'] == 'oembed':
            content_html += utils.add_embed(content['url'])
        elif content['_type'] == 'embed':
            if 'instagram-media' in content['html']:
                m = re.search(r'data-instgrm-permalink="([^"]+)"', content['html'])
                content_html += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled content type embed')
        elif content['_type'] == 'relatedMaterial':
            content_html += '<p><strong>Related:</strong> <a href="https://www.theartnewspaper.com/{}">{}</a></p>'.format(content['material']['permalink'], content['material']['headline'])
        else:
            logger.warning('unhandled content type ' + content['_type'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    utils.write_file(next_data, './debug/debug.json')

    article_json = next_data['pageProps']['doc']['_0']
    item = {}
    item['id'] = article_json['_id']
    item['url'] = 'https://www.theartnewspaper.com/' + article_json['permalink']
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['publishedAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_json.get('_updatedAt'):
        dt = datetime.fromisoformat(article_json['_updatedAt'])
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = ''
    authors = []
    prefix = ''
    for it in article_json['authors']:
        if it['_type'] == 'authorsPrefixString':
            if prefix:
                # Switch prefixes
                if item['author'].get('name'):
                    item['author']['name'] += '; '
                item['author']['name'] += prefix + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
                authors = []
            prefix = it['text'] + ' '
        elif it['_type'] == 'author':
            authors.append(it['fullName'])
    if item['author'].get('name'):
        item['author']['name'] += '; '
    if authors:
        item['author']['name'] += prefix + re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('keywords'):
        item['tags'] = []
        for it in article_json['keywords']:
            item['tags'].append(it['name'])

    item['content_html'] = ''
    if article_json.get('standfirst'):
        item['content_html'] += '<p><em>' + article_json['standfirst'] + '</em></p>'

    if article_json.get('mainImage'):
        item['_image'] = resize_image(article_json['mainImage']['asset']['_id'])
        if article_json['mainImage'].get('caption'):
            caption = render_content(article_json['mainImage']['caption'][0]['children'])
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['_image'], caption)

    if article_json.get('mainMedia'):
        item['content_html'] += utils.add_embed(article_json['mainMedia'])

    if article_json.get('body'):
        item['content_html'] += render_content(article_json['body'])

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
