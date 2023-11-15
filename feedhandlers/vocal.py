import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlsplit

import utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1024):
    split_url = urlsplit(img_src)
    if 'images.unsplash.com' in img_src:
        query = parse_qs(split_url.query)
        if query.get('w'):
            query['w'][0] = width
        else:
            query['w'] = [width]
        return '{}://{}{}?{}'.format(split_url.scheme, split_url.netloc, split_url.path, urlencode(query, doseq=True))
    elif 'res.cloudinary.com' in img_src:
        paths = list(filter(None, split_url.path.split('/')))
        return 'https://res.cloudinary.com/{}/image/upload/d_642250b563292b35f27461a7.png,f_jpg,fl_progressive,q_auto,w_{}/{}'.format(paths[0], width, paths[-1])
    return img_src


def render_document(nodes, images, embeds):
    content_html = ''
    for node in nodes:
        if node['object'] == 'text':
            start_tag = ''
            end_tag = ''
            if node.get('marks'):
                for mark in node['marks']:
                    if mark['type'] == 'bold':
                        start_tag += '<b>'
                        end_tag = '</b>' + end_tag
                    elif mark['type'] == 'italic':
                        start_tag += '<i>'
                        end_tag = '</i>' + end_tag
                    elif mark['type'] == 'underline':
                        start_tag += '<u>'
                        end_tag = '</u>' + end_tag
                    else:
                        logger.warning('unhandled mark type ' + mark['type'])
            content_html += start_tag + node['text'] + end_tag
        elif node['object'] == 'block':
            if node['type'] == 'paragraph':
                content_html += '<p>' + render_document(node['nodes'], images, embeds) + '</p>'
            elif node['type'] == 'heading':
                content_html += '<h2>' + render_document(node['nodes'], images, embeds) + '</h2>'
            elif node['type'] == 'cloudinaryImage' or node['type'] == 'unsplashImage':
                for id in node['data']['_joinIds']:
                    image = next((it for it in images if it['id'] == id), None)
                    if image:
                        captions = []
                        block = next((it for it in node['nodes'] if (it.get('type') and it['type'] == 'caption')), None)
                        if block:
                            caption = render_document(block['nodes'], images, embeds)
                            captions.append(caption)
                        if image['__typename'] == '_Block_Post_unsplashImage' and image['image'].get('user'):
                            caption = 'Photo by <a href="{}">{}</a> on <a href="https://unsplash.com/">Unsplash</a>'.format(image['image']['user']['url'], image['image']['user']['name'])
                            captions.append(caption)
                        content_html += utils.add_image(resize_image(image['image']['publicUrl']), ' | '.join(captions))
                    else:
                        logger.warning('unknown {} id {}'.format(node['type'], id))
            elif node['type'] == 'oEmbed':
                for id in node['data']['_joinIds']:
                    embed = next((it for it in embeds if it['id'] == id), None)
                    if embed:
                        # if embed['__typename'] != '_Block_Post_oEmbed':
                        if 'https://vocal.media' in embed['embed']['originalUrl']:
                            if '/challenges' not in embed['embed']['originalUrl']:
                                embed_item = get_content(embed['embed']['originalUrl'], {"embed": True}, None, False)
                                if embed_item:
                                    content_html += embed_item['content_html']
                        elif 'https://awards.vocal.media' in embed['embed']['originalUrl']:
                            pass
                        else:
                            content_html += utils.add_embed(embed['embed']['originalUrl'])
                    else:
                        logger.warning('unknown oEmbed id ' + id)
            elif node['type'] == 'blockquote':
                content_html += utils.add_blockquote(render_document(node['nodes'], images, embeds))
            elif node['type'] == 'unordered-list':
                content_html += '<ul>' + render_document(node['nodes'], images, embeds) + '</ul>'
            elif node['type'] == 'ordered-list':
                content_html += '<ol>' + render_document(node['nodes'], images, embeds) + '</ol>'
            elif node['type'] == 'list-item':
                content_html += '<li>' + render_document(node['nodes'], images, embeds) + '</li>'
            else:
                logger.warning('unhandled block type ' + node['type'])
        elif node['object'] == 'inline':
            if node['type'] == 'link':
                content_html += '<a href="{}">{}</a>'.format(node['data']['href'], render_document(node['nodes'], images, embeds))
            else:
                logger.warning('unhandled inline type ' + node['type'])
        else:
            logger.warning('unhandled node object ' + node['object'])
    return content_html


def get_content(url, args, site_json, save_debug=False, site_id=''):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "authorization": "",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"118\", \"Microsoft Edge\";v=\"118\", \"Not=A?Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "vocal-platform-type": "web",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.61"
    }

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if not site_id:
        if paths[0] == 'resources':
            site_id = '589bb183-c447-49ba-9977-11986bda37c3'
        else:
            api_url = 'https://vocal.media/admin/api?operationName=VocalSite&variables=%7B%22siteSlug%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%2218dce912c3f050d6a245211e2995ab4e951d6f7e10058b45a3af57cd42b2b95c%22%7D%7D'.format(paths[0])
            api_json = utils.get_url_json(api_url, headers=headers)
            if not api_json:
                return None
            site_id = api_json['data']['allSites'][0]['id']

    api_url = 'https://vocal.media/admin/api?operationName=Post&variables=%7B%22siteId%22%3A%22{}%22%2C%22postSlug%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%222042cff4ade4d390c99b2970b9ddf60c42ed0cabe22a6570fd4f0b2cd5c39498%22%7D%7D'.format(site_id, paths[1])
    api_json = utils.get_url_json(api_url, headers=headers)
    if not api_json:
        return None

    post_json = api_json['data']['allPosts'][0]
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']
    if post_json['vocalSite']['slug'] == 'vocal':
        item['url'] = 'https://vocal.media/resources/{}'.format(post_json['slug'])
    else:
        item['url'] = 'https://vocal.media/{}/{}'.format(post_json['vocalSite']['slug'], post_json['slug'])
    item['title'] = post_json['name']

    dt = datetime.fromisoformat(post_json['publishedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['contentUpdatedAt'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()

    item['author'] = {"name": post_json['author']['name']}

    if post_json.get('tags'):
        item['tags'] = []
        for it in post_json['tags']:
            item['tags'].append(it['name'])

    if post_json.get('summary'):
        item['summary'] = post_json['summary']

    caption = ''
    if post_json.get('heroImage'):
        item['_image'] = post_json['heroImage']['large']
        if post_json.get('heroImageCaption'):
            caption = post_json['heroImageCaption']
    elif post_json.get('heroUnsplashImage'):
        item['_image'] = post_json['heroUnsplashImage']['publicUrl']
        if post_json['heroUnsplashImage'].get('user'):
            caption = 'Photo by <a href="{}">{}</a> on <a href="https://unsplash.com/">Unsplash</a>'.format(post_json['heroUnsplashImage']['user']['url'], post_json['heroUnsplashImage']['user']['name'])

    if 'embed' in args:
        item['content_html'] = '<div style="display:flex; flex-wrap:wrap; border:1px solid black;">'
        if item.get('_image'):
            item['content_html'] += '<div style="flex:1; min-width:400px; margin:auto;"><img src="{}" style="display:block; width:100%;"/></div>'.format(item['_image'])
        item['content_html'] += '<div style="flex:1; min-width:256px; margin:auto; padding:8px;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div><div>By {}</div>'.format(item['url'], item['title'], item['author']['name'])
        if post_json.get('subtitle'):
            item['content_html'] += '<div><em>{}</em></div>'.format(post_json['subtitle'])
        item['content_html'] += '</div></div>'
        return item

    item['content_html'] = ''
    if post_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['subtitle'])

    if item.get('_image'):
        item['content_html'] += utils.add_image(resize_image(item['_image']), caption)

    document = json.loads(post_json['content']['document'])
    if save_debug:
        utils.write_file(document, './debug/doc.json')

    images = post_json['content']['heroImages'] + post_json['content']['images'] + post_json['content']['unsplashImages']
    item['content_html'] += render_document(document['nodes'], images, post_json['content']['oEmbeds'])

    return item


def get_feed(url, args, site_json, save_debug=False):
    feed_title = ''
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "authorization": "",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "pragma": "no-cache",
        "sec-ch-ua": "\"Chromium\";v=\"118\", \"Microsoft Edge\";v=\"118\", \"Not=A?Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "vocal-platform-type": "web",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.61"
    }

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    if len(paths) == 0 or paths[0] == 'latest-stories':
        api_url = 'https://vocal.media/admin/api?operationName=allPosts&variables=%7B%22orderBy%22%3A%22publishedAt_DESC%22%2C%22vocalSite%22%3A%7B%7D%2C%22pageSize%22%3A12%2C%22skip%22%3A0%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22683fb1acf13ba09ad5cb1706998723422383d4e9c5ba6a1cca4283a1191e7492%22%7D%7D'
        key = 'allPosts'
    elif paths[0] == 'top-stories':
        api_url = 'https://vocal.media/admin/api?operationName=allPosts&variables=%7B%22orderBy%22%3A%22editorPickAt_DESC%22%2C%22vocalSite%22%3A%7B%7D%2C%22isEditorPick%22%3Atrue%2C%22pageSize%22%3A10%2C%22skip%22%3A0%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22683fb1acf13ba09ad5cb1706998723422383d4e9c5ba6a1cca4283a1191e7492%22%7D%7D'
        key = 'allPosts'
    elif paths[0] == 'resources':
        # Not sure if this is constant
        site_id = '589bb183-c447-49ba-9977-11986bda37c3'
        if len(paths) > 1 and paths[1] == 'tag':
            api_url = 'https://vocal.media/admin/api?operationName=ResourceTags&variables=%7B%22siteId%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%229de87ec202565f10c51cb665368c16d7e0ddf569e1647b70244e72f850d0c09e%22%7D%7D'.format(site_id)
            api_json = utils.get_url_json(api_url, headers=headers)
            if not api_json:
                return None
            tag = next((it for it in api_json['data']['allTags'] if it['slug'] == paths[2]), None)
            if not tag:
                logger.warning('unable to determine tag id')
                return None
            api_url = 'https://vocal.media/admin/api?operationName=allPosts&variables=%7B%22orderBy%22%3A%22publishedAt_DESC%22%2C%22vocalSite%22%3A%7B%22id%22%3A%22{}%22%7D%2C%22tagsWhere%22%3A%7B%22id%22%3A%22{}%22%7D%2C%22pageSize%22%3A12%2C%22skip%22%3A0%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22683fb1acf13ba09ad5cb1706998723422383d4e9c5ba6a1cca4283a1191e7492%22%7D%7D'.format(site_id, tag['id'])
        else:
            api_url = 'https://vocal.media/admin/api?operationName=allPosts&variables=%7B%22orderBy%22%3A%22publishedAt_DESC%22%2C%22vocalSite%22%3A%7B%22id%22%3A%22{}%22%7D%2C%22pageSize%22%3A12%2C%22skip%22%3A0%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22683fb1acf13ba09ad5cb1706998723422383d4e9c5ba6a1cca4283a1191e7492%22%7D%7D'.format(site_id)
        key = 'allPosts'
    elif paths[0] == 'authors':
        api_url = 'https://vocal.media/admin/api?operationName=Author&variables=%7B%22authorSlug%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22c2042d06c1db6b7b253094eadee4bd5722b3189230f344da36fcc6ad22ff6346%22%7D%7D'.format(paths[1])
        api_json = utils.get_url_json(api_url, headers=headers)
        if not api_json:
            return None
        author_id = api_json['data']['allUsers'][0]['id']
        api_url = 'https://vocal.media/admin/api?operationName=allPosts&variables=%7B%22orderBy%22%3A%22publishedAt_DESC%22%2C%22pageSize%22%3A12%2C%22vocalSite%22%3A%7B%7D%2C%22userId%22%3A%22{}%22%2C%22skip%22%3A0%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%2269c8a1ea77bac4c37d2946582c0267eec74a9139d03b4dad650ce6e21d4a4a5d%22%7D%7D'.format(author_id)
        key = 'posts'
    else:
        api_url = 'https://vocal.media/admin/api?operationName=VocalSite&variables=%7B%22siteSlug%22%3A%22{}%22%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%2218dce912c3f050d6a245211e2995ab4e951d6f7e10058b45a3af57cd42b2b95c%22%7D%7D'.format(paths[0])
        api_json = utils.get_url_json(api_url, headers=headers)
        if not api_json:
            return None
        site_id = api_json['data']['allSites'][0]['id']
        feed_title = '{} | vocal.media'.format(api_json['data']['allSites'][0]['name'])
        api_url = 'https://vocal.media/admin/api?operationName=allPosts&variables=%7B%22orderBy%22%3A%22publishedAt_DESC%22%2C%22vocalSite%22%3A%7B%22id%22%3A%22{}%22%7D%2C%22pageSize%22%3A8%7D&extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22683fb1acf13ba09ad5cb1706998723422383d4e9c5ba6a1cca4283a1191e7492%22%7D%7D'.format(site_id)
        key = 'allPosts'

    api_json = utils.get_url_json(api_url, headers=headers)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for post in api_json['data'][key]:
        if post['vocalSite']['slug'] == 'vocal':
            post_url = 'https://vocal.media/resources/{}'.format(post['slug'])
        else:
            post_url = 'https://vocal.media/{}/{}'.format(post['vocalSite']['slug'], post['slug'])
        if save_debug:
            logger.debug('getting content for ' + post_url)
        item = get_content(post_url, args, site_json, save_debug, site_id=post['vocalSite']['id'])
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed = utils.init_jsonfeed(args)
    feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed