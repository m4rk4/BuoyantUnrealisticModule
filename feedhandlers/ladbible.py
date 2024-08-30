import json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import jwplayer

import logging

logger = logging.getLogger(__name__)


def get_next_json(url, save_debug):
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "priority": "u=1, i",
        "rsc": "1",
        "sec-ch-ua": "\"Chromium\";v=\"124\", \"Microsoft Edge\";v=\"124\", \"Not-A.Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin"
    }
    next_data = utils.get_url_html(url, headers=headers)
    if not next_data:
        logger.warning('unable to get next data from ' + url)
        return None
    if save_debug:
        utils.write_file(next_data, './debug/next.txt')

    next_json = {}
    x = 0
    m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data)
    while m:
        key = m.group(1)
        x += len(key) + 1
        val = m.group(2)
        if val.startswith('I'):
            val = val[1:]
            x += 1
        elif val.startswith('HL'):
            val = val[2:]
            x += 2
        elif val.startswith('T'):
            t = re.search(r'T([0-9a-f]+),(.*)', val)
            if t:
                n = int(t.group(1), 16)
                x += len(t.group(1)) + 2
                val = next_data[x:x + n]
                # if not val.isascii():
                #     i = n
                #     n = 0
                #     for c in val:
                #         n += 1
                #         i -= len(c.encode('utf-8'))
                #         if i == 0:
                #             break
                #     val = next_data[x:x + n]
        if val:
            # print(key, val)
            if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
                next_json[key] = json.loads(val)
            else:
                next_json[key] = val
            x += len(val)
            if next_data[x:].startswith('\n'):
                x += 1
            m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data[x:])
        else:
            break
    return next_json


def resize_image(img_src, width=1080):
    return 'https://images.ladbible.com/resize?type=webp&quality=70&width={}&fit=contain&gravity=auto&url=https://images.ladbiblegroup.com{}'.format(width, urlsplit(img_src).path)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if '/jw-iframe' in split_url.path:
        params = parse_qs(split_url.query)
        if 'videoId' in params:
            return jwplayer.get_content('https://cdn.jwplayer.com/v2/media/{}?page_domain={}'.format(params['videoId'][0], split_url.netloc), args, {}, False)
        else:
            logger.warning('unknown videoId for ' + url)
            return None

    next_json = get_next_json(url, save_debug)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/next.json')

    def find_child(children, key, val):
        for child in children:
            if isinstance(child, list) and child[0] == '$' and isinstance(child[3], dict):
                if key in child[3]:
                    if isinstance(child[3][key], str):
                        if val in child[3][key]:
                            return child
                    else:
                        return child
                if 'children' in child[3]:
                    c = find_child(child[3]['children'], key, val)
                    if c:
                        return c
        return None

    article_json = None
    article_body = None
    if isinstance(next_json['2'], list) and next_json['2'][0] == '$' and next_json['2'][1] == 'main':
        article_template = find_child(next_json['2'][3]['children'], 'className', 'article-template_articleTemplate')
        if article_template:
            article_json = article_template[3]['article']
            article_body = find_child(article_template[3]['children'], 'className', 'article-template_body')
    if not article_json:
        logger.warning('unable to find article json in ' + url)
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = '{}://{}{}'.format(split_url.scheme, split_url.netloc, article_json['staticLink'])
    item['title'] = article_json['title']

    dt = datetime.fromisoformat(article_json['publishedAtUTC'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['updatedAtUTC'])
    item['date_modified'] = dt.isoformat()

    item['author'] = {"name": article_json['author']['name']}

    item['tags'] = []
    for it in article_json['categories']:
        item['tags'].append(it['name'])
    for it in article_json['tags']:
        item['tags'].append(it['name'])

    if article_json.get('metaDescription'):
        item['summary'] = article_json['metaDescription']
    elif article_json.get('summary'):
        item['summary'] = article_json['summary']

    item['content_html'] = ''
    if article_json.get('summary'):
        item['content_html'] += '<p><em>' + article_json['summary'] + '</em></p>'

    if article_json.get('featuredVideo'):
        item['_image'] = article_json['featuredImage']
        #item['content_html'] += utils.add_video(article_json['featuredVideo'], 'video/mp4', article_json['featuredImage'], article_json['featuredVideoInfo'].get('title'))
        item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/' + article_json['featuredVideoInfo']['id'])
    elif article_json.get('featuredImage'):
        item['_image'] = article_json['featuredImage']
        item['content_html'] += utils.add_image(resize_image(item['_image']), article_json['featuredImageInfo']['credit'].get('text'), link=item['_image'])

    if 'embed' in args:
        item['content_html'] = '<div style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(split_url.netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}" target="_blank">Read</a></p></div></div><div>&nbsp;</div>'.format(config.server, quote_plus(item['url']))
        return item

    if article_body:
        if save_debug:
            utils.write_file(article_body, './debug/body.json')

        def format_child(child):
            nonlocal next_json
            child_html = ''
            if isinstance(child, str):
                if child.isascii():
                    return child
                else:
                    try:
                        return child.encode('iso-8859-1').decode('utf-8')
                    except:
                        return child
            elif isinstance(child, list) and len(child) > 0 and isinstance(child[0], str) and child[0] == '$':
                start_tag = ''
                end_tag = ''
                skip_children = False
                if 'className' in child[3]:
                    if 'text_text_' in child[3]['className']:
                        if child[1] == 'br' or child[1] == 'hr':
                            start_tag = '<{}/>'.format(child[1])
                            end_tag = ''
                            skip_children = True
                        else:
                            start_tag = '<{}>'.format(child[1])
                            end_tag = '</{}>'.format(child[1])
                    elif 'link_link_' in child[3]['className']:
                        start_tag = '<a href="{}">'.format(child[3]['href'])
                        end_tag = '</a>'
                    elif 'article-image_articleImage_' in child[3]['className']:
                        image_html = format_children(child[3]['children'])
                        m = re.search(r'<cite>(.*?)</cite>', image_html)
                        if m:
                            caption = m.group(1)
                        else:
                            caption = ''
                        m = re.search(r'src="([^"]+)"', image_html)
                        if m:
                            img_src = m.group(1)
                            child_html += utils.add_image(resize_image(img_src), caption, link=img_src)
                            skip_children = True
                        else:
                            logger.warning('unhandled image class ' + child[3]['className'])
                    elif 'article-image_imageWrapper_' in child[3]['className']:
                        start_tag = '<figure>'
                        end_tag = '</figure>'
                    elif 'image-credit_imageCredit_' in child[3]['className']:
                        start_tag = '<{}>'.format(child[1])
                        end_tag = '</{}>'.format(child[1])
                    elif 'reddit-card' in child[3]['className']:
                        child_html += utils.add_embed(child[3]['children'][3]['href'])
                        skip_children = True
                    elif 'tiktok-embed_tiktok_' in child[3]['className']:
                        pass
                    elif 'topics-list_topic_' in child[3]['className'] or 'article-tags_tagsContainer_' in child[3]['className']:
                        skip_children = True
                    else:
                        logger.warning('unhandled className ' + child[3]['className'])
                elif child[1][0] != '$':
                    if child[1] == 'iframe':
                        child_html += utils.add_embed(child[3]['src'])
                    elif child[1] == 'script':
                        skip_children = True
                    else:
                        start_tag = '<{}>'.format(child[1])
                        end_tag = '</{}>'.format(child[1])
                elif child[1].startswith('$L'):
                    key = child[1][2:]
                    if key in next_json and isinstance(next_json[key], list) and len(next_json[key]) > 2 and isinstance(next_json[key][2], str):
                        if next_json[key][2] == 'ResizableImage':
                            child_html += '<img src="{}"/>'.format(child[3]['src'])
                            skip_children = True
                        elif next_json[key][2] == 'ArticleVideoPlayer':
                            child_html += utils.add_embed(child[3]['attribs']['src'])
                            skip_children = True
                        elif next_json[key][2] == 'YouTubeEmbed':
                            child_html += utils.add_embed('https://www.youtube.com/watch?v=' + child[3]['id'])
                            skip_children = True
                        elif next_json[key][2] == 'TwitterEmbed':
                            child_html += utils.add_embed('https://twitter.com/__/status/' + child[3]['id'])
                            skip_children = True
                        elif next_json[key][2] == 'InstagramEmbed':
                            child_html += utils.add_embed(child[3]['url'])
                            skip_children = True
                        elif next_json[key][2] == '':
                            skip_children = True
                        else:
                            print(next_json[key][2])
                if not skip_children:
                    child_html += start_tag
                    # print(child)
                    if 'children' in child[3] and child[3].get('children'):
                        child_html += format_children(child[3]['children'])
                    child_html += end_tag
            elif isinstance(child, list) and len(child) > 0 and isinstance(child[0], list):
                for c in child:
                    child_html += format_child(c)
            return child_html

        def format_children(children):
            if isinstance(children, str) or (isinstance(children, list) and len(children) > 0 and isinstance(children[0], str) and children[0] == '$'):
                return format_child(children)
            elif isinstance(children, list):
                children_html = ''
                for child in children:
                    children_html += format_child(child)
                return children_html

        item['content_html'] += format_children(article_body[3]['children'])

    return item


def get_feed(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, save_debug)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/next.json')

    cards = None
    for key, val in next_json.items():
        if isinstance(val, list) and len(val) == 4 and val[0] == '$' and val[1] == 'section' and isinstance(val[3], dict) and 'className' in val[3] and 'card-loop_container_' in val[3]['className']:
            cards = val[3]['children']
            break
    if not cards:
        logger.warning('unable to find card-loop_container in ' + url)
        return None

    card_list = None
    for val in cards:
        if isinstance(val, list) and len(val) == 4 and val[0] == '$' and val[1] == 'ul' and isinstance(val[3], dict) and 'className' in val[3] and 'card-loop_cardList_' in val[3]['className']:
            card_list = val[3]['children']
            break
    if not card_list:
        logger.warning('unable to find card-loop_cardList_ in ' + url)
        return None

    def find_child(children, key, val):
        if isinstance(children, list) and len(children) == 4 and isinstance(children[0], str) and children[0] == '$' and isinstance(children[3], dict):
            if key in children[3]:
                if isinstance(children[3][key], str) and val:
                    if val in children[3][key]:
                        return children
                else:
                    return children
            if 'children' in children[3]:
                c = find_child(children[3]['children'], key, val)
                if c:
                    return c
        elif isinstance(children, list):
            for child in children:
                if isinstance(child, list) and len(child) == 4 and isinstance(child[0], str) and child[0] == '$' and isinstance(child[3], dict):
                    if key in child[3]:
                        if isinstance(child[3][key], str) and val:
                            if val in child[3][key]:
                                return child
                        else:
                            return child
                    if 'children' in child[3]:
                        c = find_child(child[3]['children'], key, val)
                        if c:
                            return c
        return None

    split_url = urlsplit(url)
    links = []
    for val in card_list:
        if isinstance(val, list) and len(val) == 4 and val[0] == '$' and val[1] == 'li' and isinstance(val[3], dict) and 'children' in val[3]:
            link = find_child(val[3]['children'], 'href', '')
            if link:
                links.append('https://' + split_url.netloc + link[3]['href'])

    n = 0
    feed_items = []
    for link in links:
        if save_debug:
            logger.debug('getting content for ' + link)
        item = get_content(link, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    #feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
