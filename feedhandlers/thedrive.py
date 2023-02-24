import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1200):
    split_url = urlsplit(img_src)
    return '{}://{}{}?auto=webp&optimize=high&quality=70&width={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def get_next_data(url, site_json):
    if not site_json.get('buildId'):
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        el = soup.find('script', id='__NEXT_DATA__')
        if not el:
            logger.warning('unable to find NEXT_DATA in ' + url)
            return None
        return json.loads(el.string)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 0:
        path = '/index'
    elif split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path
    path += '.json'

    next_url = '{}://{}/_next/data/{}{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
    next_data = utils.get_url_json(next_url, retries=1)
    if not next_data:
        page_html = utils.get_url_html(url)
        m = re.search(r'"buildId":"([^"]+)"', page_html)
        if m and m.group(1) != site_json['buildId']:
            logger.debug('updating {} buildId'.format(split_url.netloc))
            site_json['buildId'] = m.group(1)
            utils.update_sites(url, site_json)
            next_url = '{}://{}/_next/data/{}/{}'.format(split_url.scheme, split_url.netloc, site_json['buildId'], path)
            next_data = utils.get_url_json(next_url)
            if not next_data:
                return None
    return next_data


def get_content(url, args, site_json, save_debug=False):
    next_data = get_next_data(url, site_json)
    if not next_data:
        return None
    #utils.write_file(next_data, './debug/next.json')

    split_url = urlsplit(url)
    if split_url.path.endswith('/'):
        path = split_url.path[:-1]
    else:
        path = split_url.path

    node_json = None
    for it in next_data['pageProps']['dehydratedState']['queries']:
        if path in it['queryKey']:
            node_json = it['state']['data']['resolveUrl']['node']
    if not node_json:
        logger.warning('unable to determine article node data in {}'.format(url))
        return None

    if save_debug:
        utils.write_file(node_json, './debug/debug.json')

    item = {}
    item['id'] = node_json['databaseId']
    item['url'] = node_json['link']
    item['title'] = node_json['title']

    dt = datetime.fromisoformat(node_json['seo']['opengraphPublishedTime'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if node_json.get('opengraphModifiedTime'):
        dt = datetime.fromisoformat(node_json['seo']['opengraphModifiedTime'])
        item['date_modified'] = dt.isoformat()

    authors = []
    for it in node_json['authorTags']['nodes']:
        authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    if node_json.get('categories') and node_json['categories'].get('nodes'):
        for it in node_json['categories']['nodes']:
            item['tags'].append(it['name'])
    if node_json.get('tags') and node_json['tags'].get('nodes'):
        for it in node_json['tags']['nodes']:
            item['tags'].append(it['name'])
    if not item.get('tags'):
        del item['tags']

    item['content_html'] = ''
    if node_json.get('excerpt'):
        item['summary'] = node_json['excerpt']
        item['content_html'] += '<p><em>{}</em></p>'.format(node_json['seo']['opengraphDescription'])

    if node_json.get('featuredImage'):
        item['_image'] = node_json['featuredImage']['node']['sourceUrl']
        captions = []
        if node_json['featuredImage']['node'].get('caption'):
            captions.append(re.sub(r'^<p>(.*)</p>$', r'\1', node_json['featuredImage']['node']['caption'].strip()))
        if node_json['featuredImage']['node'].get('mediaAdditionalData'):
            if node_json['featuredImage']['node']['mediaAdditionalData'].get('mediaSubtitle'):
                captions.append(node_json['featuredImage']['node']['mediaAdditionalData']['mediaSubtitle'])
            if node_json['featuredImage']['node']['mediaAdditionalData'].get('mediaCredit') and node_json['featuredImage']['node']['mediaAdditionalData']['mediaCredit'].get('mcName'):
                captions.append(node_json['featuredImage']['node']['mediaAdditionalData']['mediaCredit']['mcName'])
        item['content_html'] += utils.add_image(resize_image(item['_image']), ' | '.join(captions))
    elif node_json.get('featuredImageUrl'):
        item['_image'] = node_json['featuredImageUrl']
        item['content_html'] += utils.add_image(resize_image(item['_image']))

    for block in node_json['blocks']:
        if block['name'] == 'core/paragraph':
            item['content_html'] += block['originalContent']
        elif block['name'] == 'core/heading':
            attrs = json.loads(block['attributesJSON'])
            item['content_html'] += '<h{0}>{1}</h{0}>'.format(attrs['level'], attrs['content'])
        elif block['name'] == 'core/image':
            captions = []
            if block['attributes'].get('caption'):
                captions.append(block['attributes']['caption'])
            if block['attributes'].get('creditText'):
                captions.append(block['attributes']['creditText'])
            item['content_html'] += utils.add_image(resize_image(block['attributes']['url']), ' | '.join(captions))
        elif block['name'] == 'core/gallery':
            captions = []
            if block['attributes'].get('caption'):
                captions.append(block['attributes']['caption'])
            if block['attributes'].get('creditText'):
                captions.append(block['attributes']['creditText'])
            for it in block['innerBlocks']:
                if it['name'] == 'core/image':
                    cap = []
                    if it['attributes'].get('caption'):
                        cap.append(it['attributes']['caption'])
                    if it['attributes'].get('creditText'):
                        cap.append(it['attributes']['creditText'])
                    item['content_html'] += utils.add_image(resize_image(it['attributes']['url']), ' | '.join(cap + captions))
        elif block['name'] == 'core/embed':
            attrs = json.loads(block['attributesJSON'])
            item['content_html'] += utils.add_embed(attrs['url'])
        elif block['name'] == 'core/list':
            attrs = json.loads(block['attributesJSON'])
            if attrs['ordered']:
                tag = 'ol'
            else:
                tag = 'ul'
            item['content_html'] += '<{}>'.format(tag)
            for it in block['innerBlocks']:
                attrs = json.loads(it['attributesJSON'])
                item['content_html'] += '<li>{}</li>'.format(attrs['content'])
            item['content_html'] += '</{}>'.format(tag)
        elif block['name'] == 'acf/product-table':
            attrs = json.loads(block['attributesJSON'])
            #utils.write_file(attrs, './debug/attrs.json')
            item['content_html'] += '<table style="border:1px solid black; border-collapse:collapse;"><tr style="border-collapse:collapse;">'
            for i in range(attrs['data']['items']):
                item['content_html'] += '<th style="border:1px solid black; border-collapse:collapse; background-color:#f68f44;"><span style="color:white;">{}</span></th>'.format(attrs['data']['items_{}_award'.format(i)].upper())
            item['content_html'] += '</tr><tr style="border-collapse:collapse;">'
            for i in range(attrs['data']['items']):
                item['content_html'] += '<td style="border-right:1px solid black; border-collapse:collapse;"><img src="{}" style="width:100%;"/></td>'.format(attrs['data']['items_{}_image_url'.format(i)])
            item['content_html'] += '</tr><tr style="border-collapse:collapse;">'
            for i in range(attrs['data']['items']):
                item['content_html'] += '<td style="text-align:center; border-right:1px solid black; border-collapse:collapse;"><span style="font-size:1.1em; font-weight:bold;">{}</span></td>'.format(attrs['data']['items_{}_product_name'.format(i)])
            item['content_html'] += '</tr><tr style="border-collapse:collapse;">'
            for i in range(attrs['data']['items']):
                item['content_html'] += '<td style="text-align:center; padding-top:0.4em; padding-bottom:0.4em; border-right:1px solid black; border-collapse:collapse;"><span style="padding:0.4em; font-weight:bold; background-color:#f68f44;"><a href="{}" style="color:white;">SEE IT</a></span></td>'.format(utils.get_redirect_url(attrs['data']['items_{}_link'.format(i)]))
            item['content_html'] += '</tr><tr style="border:1px solid black; border-collapse:collapse;">'
            for i in range(attrs['data']['items']):
                item['content_html'] += '<td style="padding:8px; vertical-align:top; border:1px solid black; border-collapse:collapse;">{}</td>'.format(attrs['data']['items_{}_summary'.format(i)])
            item['content_html'] += '</tr><tr style="border:1px solid black; border-collapse:collapse;">'
            for i in range(attrs['data']['items']):
                item['content_html'] += '<td style="padding:8px; vertical-align:top; border:1px solid black; border-collapse:collapse;"><b>Pros:</b>{}</td>'.format(attrs['data']['items_{}_pros'.format(i)])
            item['content_html'] += '</tr><tr style="border:1px solid black; border-collapse:collapse;">'
            for i in range(attrs['data']['items']):
                item['content_html'] += '<td style="padding:8px; vertical-align:top; border:1px solid black; border-collapse:collapse;"><b>Cons:</b>{}</td>'.format(attrs['data']['items_{}_cons'.format(i)])
            item['content_html'] += '</tr></table>'
        elif block['name'] == 'acf/product-card':
            attrs = json.loads(block['attributesJSON'])
            #utils.write_file(attrs, './debug/attrs.json')
            item['content_html'] += '<div style="margin:1em; border:1px solid black;">'
            if attrs['data'].get('empire_pc_award'):
                item['content_html'] += '<div style="margin-top:0.4em; margin-bottom:1em; text-align:center;"><span style="padding:0.4em; font-size:1.1em; color:white; background-color:#f68f44">{}</span></div>'.format(attrs['data']['empire_pc_award'].upper())
            item['content_html'] += '<div style="text-align:center;"><span style="font-size:1.2em; font-weight:bold;">{}</span></div>'.format(attrs['data']['empire_pc_title'])
            item['content_html'] += utils.add_image(attrs['data']['empire_pc_direct_image_url'])
            item['content_html'] += '<div style="margin-top:1em; text-align:center;"><span style="padding:0.4em 4em; 0.4em; 4em; font-size:1.1em; font-weight:bold; background-color:#f68f44;"><a href="{}" style="color:white;">SEE IT</a></span></div>'.format(utils.get_redirect_url(attrs['data']['empire_pc_amazon_link']))
            item['content_html'] += '<div style="margin:1em;">{}</div>'.format(attrs['data']['empire_pc_description'])
            item['content_html'] += '</div>'
        elif block['name'] == 'yoast/faq-block':
            attrs = json.loads(block['attributesJSON'])
            #utils.write_file(attrs, './debug/attrs.json')
            for it in attrs['questions']:
                item['content_html'] += '<h3>{}</h3><p>{}</p>'.format(it['jsonQuestion'], it['jsonAnswer'])
        elif block['name'] == 'core/freeform':
            attrs = json.loads(block['attributesJSON'])
            if attrs.get('content'):
                logger.warning('unhandled core/freeform block in ' + item['url'])
        elif block['name'] == 'acf/related-articles-inline':
            pass
        else:
            logger.warning('unhandled {} block in {}'.format(block['name'], item['url']))

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
