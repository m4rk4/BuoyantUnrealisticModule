import re
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    api_url = 'https://api2.dwell.com/v2/slugs?url=' + quote_plus(paths[-1])

    # Authorization found in https://www.dwell.com/build/public/8ffd6474407ca118b3f4/main.js
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "authorization": "Basic ZHdlbGwtd2ViLWNsaWVudDplNGY5MTQ2MzcyNmU1ZTdiZjM2YzY0ZWQwYjE3OGEwNjU2YjIwYTQz",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"125\", \"Chromium\";v=\"125\", \"Not.A/Brand\";v=\"24\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site"
    }
    api_json = utils.get_url_json(api_url, headers=headers)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    story_url = ''
    for it in api_json['data']:
        if it['attributes']['slug'] == paths[-1]:
            story_url = it['links']['related']
            break
    if not story_url:
        logger.warning('unable to determine story id for ' + url)
        return None

    story_json = utils.get_url_json(story_url, headers=headers)
    if save_debug:
        utils.write_file(story_json, './debug/debug.json')
    story_attr = story_json['data']['attributes']

    item = {}
    item['id'] = story_attr['id']
    item['url'] = url
    item['title'] = story_attr['title']

    dt = datetime.fromisoformat(story_attr['firstPublishedAt'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if story_attr.get('updatedAt'):
        dt = datetime.fromisoformat(story_attr['updatedAt'])
        item['date_modified'] = dt.isoformat()

    authors = []
    for inc in story_json['included']:
        if inc['type'] == 'contributors' and inc['attributes']['type'] != 'Published by' and inc['attributes']['type'] != 'Brand' and inc['attributes']['type'] != 'Seller':
            author = next((it for it in story_json['included'] if (it['type'] == 'users' and it['id'] == inc['attributes']['contributorId'])), None)
            if author and author['attributes']['displayName'] != 'Dwell':
                if inc['attributes']['type'].lower() == 'written by':
                    authors.append(author['attributes']['displayName'])
                else:
                    authors.append('{} ({})'.format(author['attributes']['displayName'], inc['attributes']['type']))
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['content_html'] = ''
    if story_attr.get('lead'):
        item['summary'] = story_attr['lead']
        item['content_html'] += '<p><em>' + story_attr['lead'] + '</em></p>'

    if story_attr.get('defaultImageId'):
        image = next((it for it in story_json['included'] if it['id'] == story_attr['defaultImageId']), None)
        if image:
            item['_image'] = image['links']['large']
            item['content_html'] += utils.add_image(image['links']['large'], link=image['links']['original'])

    if story_attr.get('body'):
        item['content_html'] += story_attr['body']
        def sub_photo(matchobj):
            nonlocal story_json
            image = None
            captions = []
            mall = re.findall(r'(\w+)=\"(.*?)\"(?=(\s\w+=|/>))', matchobj.group(0))
            for m in mall:
                if m[0] == 'photoId':
                    image = next((it for it in story_json['included'] if it['id'] == m[1]), None)
                elif m[0] == 'caption':
                    if m[1].lower() != 'add a caption':
                        captions.insert(0, m[1])
                elif m[0] == 'credit':
                    if m[1].lower() != 'add credit':
                        captions.append(m[1])
            if image:
                return utils.add_image(image['links']['large'], ' | '.join(captions), link=image['links']['original'])
            else:
                logger.warning('unhandled dwell-photo ' + matchobj.group(0))
        item['content_html'] = re.sub(r'<dwell-photo.*?/>', sub_photo, item['content_html'])

        def sub_embed(matchobj):
            m = re.search(r'source="([^"]+)"', matchobj.group(0))
            if m.group(1) == 'instagram':
                embed_url = 'https://www.instagram.com/'
                m = re.search(r'type="([^"]+)"', matchobj.group(0))
                embed_url += m.group(1) + '/'
                m = re.search(r'id="([^"]+)"', matchobj.group(0))
                embed_url += m.group(1) + '/'
                return utils.add_embed(embed_url)
            else:
                logger.warning('unhandled dwell-embed source ' + m.group(1))
                return ''
        item['content_html'] = re.sub(r'<dwell-embed.*?/>', sub_embed, item['content_html'])

        def sub_story(matchobj):
            nonlocal story_json
            m = re.search(r'story-type="([^"]+)"', matchobj.group(0))
            if m.group(1) == 'product':
                m = re.search(r'story-id="([^"]+)"', matchobj.group(0))
                product = next((it for it in story_json['included'] if it['id'] == m.group(1)), None)
                if product:
                    product_html = '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                    if product['attributes'].get('defaultImageId'):
                        image = next((it for it in story_json['included'] if it['id'] == product['attributes']['defaultImageId']), None)
                        if image:
                            product_html += '<div style="flex:1; min-width:256px;"><img src="{}" style="width:100%;"/></div>'.format(image['links']['medium'])
                    link = None
                    if product['attributes']['shopLinkType'] == 'sponsored':
                        for data in product['relationships']['sponsors']['data']:
                            if data['type'] == 'links':
                                link = next((it for it in story_json['included'] if it['id'] == data['id']), None)
                                if link:
                                    break
                    else:
                        logger.warning('unhandled product shopLinkType ' + product['attributes']['shopLinkType'])
                    price = None
                    sale = None
                    if product['relationships']['metadata'].get('data'):
                        for data in product['relationships']['metadata']['data']:
                            metadata = next((it for it in story_json['included'] if it['id'] == data['id']), None)
                            if metadata:
                                if metadata['attributes']['name'] == 'price':
                                    price = metadata
                                elif metadata['attributes']['name'] == 'sale price':
                                    sale = metadata
                    if link:
                        product_html += '<div style="flex:2; min-width:256px;">'
                        product_html += '<div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(link['attributes']['url'], product['attributes']['title'])
                        if price:
                            if sale:
                                product_html += '<div><s>${:,.2f}</s> <a href="{}">${:,.2f}</a></div>'.format(float(price['attributes']['value']), link['attributes']['url'], float(sale['attributes']['value']))
                            else:
                                product_html += '<div><a href="{}">${:,.2f}</a></div>'.format(link['attributes']['url'], float(price['attributes']['value']))
                        if link['attributes'].get('userId'):
                            user = next((it for it in story_json['included'] if (it['type'] == 'users' and it['id'] == link['attributes']['userId'])), None)
                            if user and user['attributes']['displayName'] != 'Dwell':
                                product_html += '<div style="font-size:0.8em;"><a href="https://www.dwell.com/@{}">{}</a></div>'.format(user['attributes']['userName'], user['attributes']['displayName'])
                        if product['attributes'].get('body'):
                            product_html += product['attributes']['body']
                        product_html += utils.add_button(link['attributes']['url'], link['attributes']['title'])
                        product_html += '</div>'
                    product_html += '</div>'
                    return product_html
            else:
                logger.warning('unhandled dwell-story type ' + m.group(1))
        item['content_html'] = re.sub(r'<dwell-story.*?/>', sub_story, item['content_html'])

        item['content_html'] = re.sub(r'<span style="[^"]*font-family[^>]+>(.*?)</span>', r'\1', item['content_html'])

        item['content_html'] = re.sub(r'<p>\s*<br/?>\s*</p>', '', item['content_html'])

        item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    # https://www.dwell.com/@dwell/rss
    return rss.get_feed(url, args, site_json, save_debug, get_content)
