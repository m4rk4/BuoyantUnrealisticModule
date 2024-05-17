import json, markdown2, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus

import config, utils

import logging

logger = logging.getLogger(__name__)


def resize_image(image, next_config, width=1200):
    return '{}/f_auto,c_limit,w_{},q_auto/{}/{}'.format(next_config['PUBLIC_GLOBAL_CLOUDINARY_DOMAINS'], width, image['raw_transformation'], image['public_id'])


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
    m = re.search(r'^([0-9a-f]{1,2}):(.*)', next_data)
    while m:
        key = m.group(1)
        x += len(key) + 1
        val = m.group(2)
        if val.startswith('I'):
            val = val[1:]
            x += 1
        elif val.startswith('T'):
            t = re.search(r'T([0-9a-f]+),(.*)', val)
            if t:
                n = int(t.group(1), 16)
                x += len(t.group(1)) + 2
                val = next_data[x:x + n]
        if val:
            if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
                next_json[key] = json.loads(val)
            else:
                next_json[key] = val
            x += len(val)
            if next_data[x:].startswith('\n'):
                x += 1
            m = re.search(r'^([0-9a-f]{1,2}):(.*)', next_data[x:])
        else:
            break
    return next_json


def get_content(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, save_debug)
    if save_debug:
        utils.write_file(next_json, './debug/debug.json')

    if not next_json.get('2'):
        return None

    ld_json = None
    article_data = None
    body_wrapper = None
    for data in next_json['2']:
        if isinstance(data[0], list):
            for it in data:
                if it[1] == 'script' and it[3]['type'] == 'application/ld+json':
                    m = re.search(r'\$L?([0-9a-f]+)', it[3]['dangerouslySetInnerHTML']['__html'])
                    key = m.group(1)
                    ld_json = next_json[key]
        elif data[3].get('articleDataLayer'):
            article_data = data[3]['articleDataLayer']
        else:
            m = re.search(r'\$L?([0-9a-f]+)', data[1])
            if m:
                key = m.group(1)
                if next_json.get(key) and 'ArticleBodyWrapper' in next_json[key]:
                    body_wrapper = data[3]

    next_config = next((it for it in next_json.values() if (isinstance(it, dict) and it.get('PUBLIC_GLOBAL_BRIGHTCOVE_ACCOUNTID'))), None)

    if not ld_json:
        logger.warning('unable to find ld+json data in ' + url)
        return None
    # if save_debug:
    #     utils.write_file(ld_json, './debug/debug.json')

    item = {}
    item['id'] = article_data['articleID']
    item['url'] = ld_json['url']
    item['title'] = article_data['contentPageTitle'].encode('iso-8859-1').decode('utf-8')
    # item['title'] = re.sub(r' \| Formula 1Â®$', '', ld_json['headline'].encode('iso-8859-1').decode('utf-8'))

    dt = datetime.fromisoformat(ld_json['datePublished'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified'])
        item['date_modified'] = dt.isoformat()

    if article_data.get('articleAuthor'):
        item['author'] = {"name": article_data['articleAuthor']}
    elif ld_json.get('author'):
        item['author'] = {"name": ld_json['author']}
    elif ld_json.get('publisher'):
        item['author'] = {"name": ld_json['publisher']['name']}

    if article_data.get('contentTags'):
        item['tags'] = article_data['contentTags'].split('|')

    if ld_json.get('image'):
        item['_image'] = ld_json['image']['url']

    if ld_json.get('description'):
        item['summary'] = ld_json['description'].encode('iso-8859-1').decode('utf-8')

    def process_children(children):
        nonlocal next_json
        nonlocal next_config
        children_html = ''
        if isinstance(children, str):
            if children.startswith('$'):
                m = re.search(r'\$L?([0-9a-f]+)', children)
                if m:
                    key = m.group(1)
                    if next_json.get(key):
                        children_html += next_json[key].encode('iso-8859-1').decode('utf-8')
            else:
                children_html += children.encode('iso-8859-1').decode('utf-8')
        elif isinstance(children, list) and len(children) > 0:
            if isinstance(children[0], str) and children[0] == '$':
                new_html = ''
                tag = ''
                key = ''
                if children[1].startswith('$'):
                    m = re.search(r'\$L?([0-9a-f]+)', children[1])
                    key = m.group(1)
                else:
                    tag = children[1]
                if tag == 'aside':
                    return ''
                if isinstance(children[3], dict) and children[3].get('children'):
                    new_html += process_children(children[3]['children'])
                if tag:
                    start_tag = '<{}>'.format(tag)
                    end_tag = '</{}>'.format(tag)
                else:
                    start_tag = ''
                    end_tag = ''
                if key and next_json.get(key) and isinstance(next_json[key], list):
                    content_type = next_json[key][2]
                    if content_type == 'Markdown':
                        new_html = markdown2.markdown(new_html)
                    elif content_type == 'ResponsiveImage':
                        img_src = ''
                        if isinstance(children[3]['image'], str) and children[3]['image'].startswith('$'):
                            if children[3]['image'] != '$undefined':
                                m = re.search(r'\$L?([0-9a-f]+)', children[3]['image'])
                                key = m.group(1)
                                if next_json.get(key):
                                    img_src = resize_image(next_json[key], next_config)
                        else:
                            img_src = resize_image(children[3]['image'], next_config)
                        if img_src:
                            start_tag = '<img src="{}" />'.format(img_src)
                    elif content_type == 'Brightcove' or content_type == 'AudioBoom' or content_type == 'AtomGallery':
                        if isinstance(children[3]['content'], str) and children[3]['content'].startswith('$'):
                            m = re.search(r'\$L?([0-9a-f]+)', children[3]['content'])
                            key = m.group(1)
                            if next_json.get(key):
                                if isinstance(next_json[key]['fields'], str) and next_json[key]['fields'].startswith('$'):
                                    m = re.search(r'\$L?([0-9a-f]+)', next_json[key]['fields'])
                                    key = m.group(1)
                                    if next_json.get(key):
                                        fields = next_json[key]
                                else:
                                    fields = next_json[key]['fields']
                        else:
                            fields = children[3]['content']['fields']
                        if content_type == 'Brightcove':
                            start_tag += utils.add_embed('https://players.brightcove.net/{}/{}_default/index.html?videoId={}'.format(next_config['PUBLIC_GLOBAL_BRIGHTCOVE_ACCOUNTID'], next_config['PUBLIC_GLOBAL_BRIGHTCOVE_PLAYERID'], fields['videoId']))
                        elif content_type == 'AudioBoom':
                            dt = datetime.fromisoformat(fields['audioPodcast']['updatedAt'])
                            poster = '{}/image?url={}&width=128&overlay=audio'.format(config.server, quote_plus(fields['audioPodcast']['postImage']))
                            start_tag = '<table><tr><td style="width:128px;"><a href="{}"><img src="{}"/></a></td><td style="vertical-align:top;"><div style="font-size:1.1em; font-weight:bold;"><a href="https:{}">{}</a></div><div>{}</div><div><small>{}</small></div></td></tr></table>'.format(
                                fields['audioPodcast']['mp3Link'], poster, fields['audioPodcast']['iFrameSrc'], fields['audioPodcast']['postTitle'].encode('iso-8859-1').decode('utf-8'), fields['audioPodcast']['channelTitle'], utils.format_display_date(dt, False))
                        elif content_type == 'AtomGallery':
                            for image in fields['imageGallery']:
                                if image.get('caption'):
                                    caption = image['caption'].encode('iso-8859-1').decode('utf-8')
                                else:
                                    caption = ''
                                start_tag += utils.add_image(resize_image(image, next_config), caption)
                    elif content_type == 'default' or content_type == 'BailoutToCSR' or content_type == 'ArticleTags' or content_type == 'ParagraphCountProvider':
                        pass
                    else:
                        logger.warning('unhandled child key {} type {}'.format(key, content_type))
                children_html += start_tag + new_html + end_tag
            elif isinstance(children[0], list):
                for child in children:
                    children_html += process_children(child)
        return children_html

    content_html = process_children(body_wrapper['children'][-1])
    content_soup = BeautifulSoup(content_html, 'html.parser')
    for el in content_soup.find('section', recursive=False):
        if not el.find('article'):
            el.decompose()

    # for el in content_soup.find_all('time'):
    for el in content_soup.find_all('h1', string=item['title']):
        it = el.find_parent('section')
        if it:
            it.decompose()

    for el in content_soup.select('p:has(> a:has(> strong:-soup-contains("READ MORE")))'):
        el.decompose()

    for el in content_soup.select('div:has(> figure:has( img))'):
        it = el.find('figcaption')
        if it:
            caption = it.get_text()
        else:
            caption = ''
        new_html = utils.add_image(el.img['src'], caption)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in content_soup.select('div:has(> blockquote)'):
        it = el.blockquote.select('div > cite')
        if it:
            author = it[0].get_text()
            quote = ''
            for i, it in enumerate(el.blockquote.find_all('p')):
                if i > 0:
                    quote += '<br/><br/>'
                quote += it.decode_contents()
            new_html = utils.add_pullquote(quote, author)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            el.blockquote['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'
            el.unwrap()

    for el in content_soup.find_all(['section', 'article']):
        el.unwrap()

    for el in content_soup.find_all('div', recursive=False):
        it = el.find('span', string='Share')
        if it:
            it.decompose()

    item['content_html'] = str(content_soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, save_debug)
    if save_debug:
        utils.write_file(next_json, './debug/feed.json')

    if not next_json.get('2'):
        return None

    if not isinstance(next_json['2'][-1], str):
        logger.warning('unexpected content format for ' + url)
        return None


    def process_children(children):
        nonlocal next_json
        articles = []
        if isinstance(children, str):
            pass
        elif isinstance(children, list) and len(children) > 0:
            if isinstance(children[0], str) and children[0] == '$':
                if children[1].startswith('$'):
                    m = re.search(r'\$L?([0-9a-f]+)', children[1])
                    key = m.group(1)
                    if key and next_json.get(key) and isinstance(next_json[key], list) and 'FilterSection' in next_json[key]:
                        articles += children[3]['items'].copy()
                elif children[1] == 'section' and children[3].get('children'):
                    articles += process_children(children[3]['children'])
            elif isinstance(children[0], list):
                for child in children:
                    articles += process_children(child)
        return articles

    m = re.search(r'\$L?([0-9a-f]+)', next_json['2'][-1])
    key = m.group(1)
    articles = process_children(next_json[key])

    n = 0
    feed_items = []
    for article in articles:
        article_url = 'https://www.formula1.com/{}/latest/article/{}.{}'.format(article['locale'], article['slug'], article['id'])
        if save_debug:
            logger.debug('getting content for ' + article_url)
        item = get_content(article_url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    # if api_json['seo'].get('metaTitle'):
    #     feed['title'] = api_json['seo']['metaTitle']
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
