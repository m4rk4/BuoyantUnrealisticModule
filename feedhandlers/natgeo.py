import json, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit, unquote_plus

import config, utils
from feedhandlers import natgeo_uk

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    split_url = urlsplit(img_src)
    return '{}://{}{}?w={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def render_body(body):
    body_html = ''
    if body['type'] == 'p':
        body_html += '<p>' + body['cntnt']['mrkup'] + '</p>'

    elif re.search(r'^h\d$', body['type']):
        body_html += '<{0}>{1}</{0}>'.format(body['type'], body['cntnt']['mrkup'])

    elif body['type'] == 'inline':
        if body['cntnt']['cmsType'] == 'editorsNote':
            body_html += '<p><em>' + body['cntnt']['note'] + '</em></p>'

        elif body['cntnt']['cmsType'] == 'image':
            captions = []
            if body['cntnt'].get('caption'):
                captions.append(re.sub(r'^<p>|</p>$', '', body['cntnt']['caption']))
            if body['cntnt'].get('credit'):
                captions.append(body['cntnt']['credit'])
            elif body['cntnt']['image'].get('crdt'):
                captions.append(body['cntnt']['image']['crdt'])
            img_src = resize_image(body['cntnt']['image']['src'])
            body_html += utils.add_image(img_src, ' | '.join(captions))

        elif body['cntnt']['cmsType'] == 'imagegroup':
            for image in body['cntnt']['images']:
                captions = []
                if image.get('caption'):
                    captions.append(re.sub(r'^<p>|</p>$', '', image['caption']))
                if image.get('credit'):
                    captions.append(image['credit'])
                elif image['image'].get('crdt'):
                    captions.append(image['image']['crdt'])
                img_src = resize_image(image['src'])
                body_html += utils.add_image(img_src, ' | '.join(captions))

        elif body['cntnt']['cmsType'] == 'photogallery':
            for image in body['cntnt']['media']:
                captions = []
                if image.get('caption'):
                    if image['caption'].get('text'):
                        captions.append(re.sub(r'^<p>|</p>$', '', image['caption']['text']))
                    if image['caption'].get('credit'):
                        captions.append(image['caption']['credit'])
                else:
                    if image['img'].get('altText'):
                        captions.append(image['img']['altText'])
                    elif image['img'].get('crdt'):
                        captions.append(image['img']['crdt'])
                img_src = resize_image(image['img']['src'])
                body_html += utils.add_image(img_src, ' | '.join(captions))

        elif body['cntnt']['cmsType'] == 'video' or body['cntnt']['cmsType'] == 'ambientVideo':
            # apikey from
            # https://assets-cdn.nationalgeographic.com/natgeo/2ffe781f47e0-release-07-28-2022.7/client/natgeo.js
            # n.SHIELD_API_KEY = "uiqlbgzdwuru14v627vdusswb"
            video_url = 'https://watch.auth.api.dtci.technology/video/auth/media/{}/asset?apikey=uiqlbgzdwuru14v627vdusswb'.format(body['cntnt']['pId'])
            # Use requests directly because a 404 error returns an error message
            r = requests.get(video_url)
            if r.text:
                video_json = r.json()
                captions = []
                if body['cntnt'].get('caption'):
                    captions.append(re.sub(r'^<p>|</p>$', '', body['cntnt']['caption']))
                elif body['cntnt'].get('description'):
                    captions.append(body['cntnt']['description'])
                elif body['cntnt'].get('slideTitle'):
                    captions.append(body['cntnt']['slideTitle'])
                if body['cntnt'].get('credit'):
                    captions.append(body['cntnt']['credit'])
                elif body['cntnt']['image'].get('crdt'):
                    captions.append(body['cntnt']['image']['crdt'])
                if video_json.get('stream'):
                    body_html += utils.add_video(video_json['stream'], 'application/x-mpegURL', body['cntnt']['image']['src'], ' | '.join(captions))
                elif video_json.get('error'):
                    captions.insert(0, '<strong>Error: {}</strong>'.format(video_json['error']))
                    poster = '{}/image?url={}&width=1000&overlay=video'.format(config.server, quote_plus(body['cntnt']['image']['src']))
                    body_html += utils.add_image(poster, ' | '.join(captions))
                else:
                    logger.warning('unhandled video json response from ' + video_url)
            else:
                logger.warning('unhandled video json response from ' + video_url)

        elif body['cntnt']['cmsType'] == 'listicle':
            body_html += '<h3>{}</h3>'.format(body['cntnt']['title'])
            if body['cntnt']['text'].startswith('<p>'):
                # convert paragraphs to list items
                text = body['cntnt']['text'].replace('<p>&nbsp;</p>', '')
                text = re.sub(r'<(/)?p>', r'<\1li>', text)
            else:
                text = '<li>' + body['cntnt']['text'].replace('<br><br>', '</li><li>') + '</li>'
            body_html += '<ul>{}</ul>'.format(text)

        elif body['cntnt']['cmsType'] == 'markup':
            logger.warning('unhandled inline markup code')
            body_html +=  '<blockquote><b>Embedded content unable to be displayed</b></blockquote>'
            #code = base64.b64decode(body['cntnt']['mrkup']).decode('utf-8')
            #utils.write_file(unquote_plus(code), './debug/markup.html')
            #soup = BeautifulSoup(unquote_plus(code), 'html.parser')

        else:
            logger.warning('unhandled inline cmsType ' + body['cntnt']['cmsType'])

    else:
        logger.warning('unhandled body type ' + body['type'])

    return body_html


def get_natgeo_json(url):
    page_html = utils.get_url_html(url)
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    el = soup.find('script', string=re.compile(r'^window\[\'__natgeo__\'\]='))
    if not el:
        logger.warning('unable to find page json in ' + url)
        return None
    return json.loads(el.string[21:-1])


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.netloc == 'www.nationalgeographic.co.uk':
        return natgeo_uk.get_content(url, args, site_json, save_debug)

    natgeo_json = get_natgeo_json(url)
    if not natgeo_json:
        return None
    page_json = natgeo_json['page']
    if save_debug:
        utils.write_file(page_json, './debug/debug.json')

    item = {}
    item['id'] = page_json['meta']['id']
    item['url'] = page_json['meta']['canonical']
    item['title'] = page_json['meta']['title']

    dt = datetime.fromisoformat(page_json['analytics']['pbDt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(page_json['analytics']['mdDt'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    contributors = {}
    for it in page_json['analytics']['cntrbGrp']:
        key = it['rl']
        contributors[key] = {}
        contributors[key]['title'] = it['title']
        names = []
        if it.get('contributors'):
            for contrib in it['contributors']:
                names.append(contrib['displayName'])
        contributors[key]['names'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(names))
    if contributors:
        if contributors.get('Writer'):
            item['author']['name'] = contributors['Writer']['names']
        for key, val in contributors.items():
            if key != 'Writer':
                item['author']['name'] += '. {} {}'.format(val['title'], val['names'])
    else:
        item['author']['name'] = 'National Geographic'

    item['tags'] = []
    for key, val in page_json['analytics']['page_taxonomy'].items():
        item['tags'] += val.split(', ')
    if not item.get('tags'):
        del item['tags']

    item['_image'] = page_json['meta']['ogMetadata']['sclImg']
    item['summary'] = page_json['meta']['description']

    item['content_html'] = ''
    for frame in page_json['content'][page_json['type']]['frms']:
        if frame and frame.get('cmsType') and frame['cmsType'] == 'ArticleBodyFrame':
            for module in frame['mods']:
                for edge in module['edgs']:
                    if edge['cmsType'] == 'ArticleBodyTile':
                        if edge.get('dscrptn'):
                            item['content_html'] += '<p><em>{}</em></p>'.format(edge['dscrptn'])
                        if edge.get('ldMda'):
                            if edge['ldMda']['type'] == 'videoLead':
                                body = {"type": "inline", "cntnt": edge['ldMda']['video']}
                            else:
                                body = {"type": "inline", "cntnt": edge['ldMda']}
                            item['content_html'] += render_body(body)
                        for body in edge['bdy']:
                            item['content_html'] += render_body(body)
                    elif edge['cmsType'] == 'ImmersiveLeadTile':
                        if edge.get('description'):
                            item['content_html'] += '<p><em>{}</em></p>'.format(edge['description'])
                        #if edge['mdiaKy'] == 'video':
                        if edge.get('video'):
                            body = {"type": "inline", "cntnt": edge['video']}
                        else:
                            body = {"type": "inline", "cntnt": edge['cmsImage']}
                        item['content_html'] += render_body(body)
                    else:
                        logger.warning('unhandled ArticleBody edge cmsType ' + edge['cmsType'])

    item['content_html'] = re.sub(r'</(figure|table)><(figure|table)', r'</\1><br/><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    split_url = urlsplit(args['url'])
    if split_url.netloc == 'www.nationalgeographic.co.uk':
        return natgeo_uk.get_feed(url, args, site_json, save_debug)

    natgeo_json = get_natgeo_json(args['url'])
    page_json = natgeo_json['page']
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    feed = utils.init_jsonfeed(args)
    feed['title'] = page_json['meta']['title']
    feed_items = []
    for frame in page_json['content']['hub']['frms']:
        for module in frame['mods']:
            if module.get('tiles'):
                for tile in module['tiles']:
                    url = tile['ctas'][0]['url']
                    if tile['ctas'][0]['icon'] == 'article':
                        if save_debug:
                            logger.debug('getting content for ' + url)
                        item = get_content(url, args, site_json, save_debug)
                        if item:
                            if utils.filter_item(item, args) == True:
                                feed_items.append(item)
                    else:
                        logger.debug('skipping content for ' + url)

    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
