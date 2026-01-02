import curl_cffi, json, re
from bs4 import BeautifulSoup, NavigableString
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_next_data(url, site_json, save_debug):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    state_tree = ["",{"children":[["section",paths[-2],"d"],{"children":[["slug",paths[-1],"c"],{"children":["__PAGE__",{}]}]}]},None,None,True]
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "next-router-state-tree": quote_plus(json.dumps(state_tree, separators=(',', ':'))),
        "priority": "u=1, i",
        "rsc": "1"
    }
    rsc_url = split_url.scheme + '://' + split_url.netloc + split_url.path + '?_rsc=' + site_json['rsc']
    r = curl_cffi.get(rsc_url, headers=headers, impersonate=config.impersonate, proxies=config.proxies)
    if r.status_code != 200:
        logger.warning('curl cffi requests status code {} getting {}'.format(r.status_code, rsc_url))
        return ''
    return r.text


def get_next_json(url, site_json, save_debug):
    next_data = get_next_data(url, site_json, save_debug)
    if not next_data:
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
                if not val.isascii():
                    i = n
                    n = 0
                    for c in val:
                        n += 1
                        i -= len(c.encode('utf-8'))
                        if i == 0:
                            break
                    val = next_data[x:x + n]
        if val:
            # print(key, val)
            if (val.startswith('{') and val.endswith('}')) or (val.startswith('[') and val.endswith(']')):
                next_json[key] = json.loads(val)
            elif val.startswith('"') and val.endswith('"'):
                next_json[key] = val[1:-1]
            else:
                next_json[key] = val
            x += len(val)
            if next_data[x:].startswith('\n'):
                x += 1
            m = re.search(r'^\s*([0-9a-f]{1,2}):(.*)', next_data[x:])
        else:
            break
    return next_json


def add_image(image, next_json):
    img_src = 'https://arc.stimg.co' + urlsplit(image['url']).path + '?w=640'
    captions = []
    if image.get('caption'):
        captions.append(image['caption'])
    photographers = []
    if image.get('photographers'):
        if isinstance(image['photographers'], str) and image['photographers'].startswith('$'):
            key = image['photographers'][1:]
            if key in next_json:
                for it in next_json[key]:
                    if isinstance(it, str) and it.startswith('$'):
                        k = it[1:]
                        if k in next_json:
                            photographer = next_json[k]
                            if photographer.get('byline'):
                                photographers.append(photographer['byline'])
                            elif photographer.get('name'):
                                photographers.append(photographer['name'])
        elif isinstance(image['photographers'], list):
            for it in image['photographers']:
                if it.get('name'):
                    photographers.append(it['name'])
                elif it.get('byline'):
                    photographers.append(it['byline'])
                elif it.get('firstName') and it.get('lastName'):
                    photographers.append(it['firstName'] + ' ' + it['lastName'])
    if photographers:
        captions.append(re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(photographers)))
    return utils.add_image(img_src, ' | '.join(captions), link=image['url'])


def get_content(url, args, site_json, save_debug=False):
    next_json = get_next_json(url, site_json, save_debug)
    if not next_json:
        return None
    if save_debug:
        utils.write_file(next_json, './debug/next.json')

    def find_article_content(data):
        if isinstance(data, list):
            if len(data) == 4 and isinstance(data[0], str) and data[0] == '$':
                if 'articleContent' in data[3]:
                    return data[3]['articleContent']
            elif len(data) == 3 and isinstance(data[0], int) and isinstance(data[2], str):
                # print(data[3])
                return None
            else:
                for val in data:
                    return find_article_content(val)
        return None
        
    for val in next_json.values():
        article_content = find_article_content(val)
        if article_content:
            break

    if not article_content:
        split_url = urlsplit(url)
        content_html = ''
        ld_json = {}
        def format_block(block):
            nonlocal split_url
            block_html = ''
            if not block:
                return ''
            elif isinstance(block, str):
                return block
            elif isinstance(block, list) and len(block) == 4 and isinstance(block[0], str) and block[0] == '$':
                # if block[1] == 'a':
                if 'href' in block[3]:
                    if 'src' in block[3]:
                        start_tag = ''
                        end_tag = ''
                    else:
                        if block[3]['href'].startswith('/'):
                            href = split_url.scheme + '://' + split_url.netloc + block[3]['href']
                        elif block[3]['href'].startswith('#'):
                            href = split_url.scheme + '://' + split_url.netloc + split_url.path + block[3]['href']
                        else:
                            href = block[3]['href']
                        start_tag = '<a href="' + href + '"'
                        if 'target' in block[3]:
                            start_tag += ' target="' + block[3]['target'] + '"'
                        start_tag += '>'
                        end_tag = '</a>'
                elif 'src' in block[3]:
                    img_src = split_url.scheme + '://' + split_url.netloc + '/_next/image?url=' + quote_plus(block[3]['src']) + '&w=1080&q=75'
                    return '<img src="' + img_src + '" style="width:100%;">'
                elif block[1] == 'figure':
                    for blk in block[3]['children']:
                        block_html += format_block(blk)
                    m = re.search(r'src="([^"]+)', block_html)
                    if m:
                        img_src = m.group(1)
                        m = re.search(r'<figcaption>(.*?)</figcaption>', block_html)
                        if m:
                            caption = m.group(1)
                        else:
                            caption = ''
                        return utils.add_image(img_src, caption)
                    else:
                        logger.warning('unhandled figure block')
                elif block[1] == 'blockquote':
                    start_tag = '<blockquote style="' + config.blockquote_style + '">'
                    end_tag = '</blockquote>'
                elif block[1] == 'script' or (block[1] == 'div' and block[2] and block[2].startswith('ad-article')):
                    return ''
                elif block[1] == 'div':
                    start_tag = '<div'
                    if 'className' in block[3]:
                        start_tag += ' class="' + block[3]['className'] + '"'
                    start_tag += '>'
                    end_tag = '</div>'
                elif block[1].startswith('$'):
                    start_tag = ''
                    end_tag = ''
                else:
                    start_tag = '<' + block[1]
                    if 'style' in block[3]:
                        start_tag += ' style="'
                        for key, val in block[3]['style'].items():
                            if key == 'fontWeight':
                                start_tag += 'font-weight:' + val + '; '
                            else:
                                logger.warning('unhandled style ' + key)
                        start_tag = start_tag.strip() + '"'
                    start_tag += '>'
                    end_tag = '</' + block[1] + '>'
                    if block[1] == 'span' and start_tag == '<span style="font-weight:400;">':
                        start_tag = ''
                        end_tag = ''
                block_html += start_tag
                if 'dangerouslySetInnerHTML' in block[3]:
                    block_html += block[3]['dangerouslySetInnerHTML']['__html']
                elif 'children' in block[3]:
                    if isinstance(block[3]['children'], str):
                        block_html += block[3]['children']
                    elif isinstance(block[3]['children'], list) and len(block[3]['children']) > 0:
                        if len(block[3]['children']) == 4 and isinstance(block[3]['children'][0], str) and block[3]['children'][0] == '$':
                            block_html += format_block(block[3]['children'])
                        else:
                            for blk in block[3]['children']:
                                block_html += format_block(blk)
                block_html += end_tag
            elif isinstance(block, list):
                for blk in block:
                    block_html += format_block(blk)
            return block_html
        for val in next_json.values():
            if isinstance(val, list):
                if len(val) == 4 and isinstance(val[0], str) and val[0] == '$' and val[1] == 'div':
                    for child in val[3]['children']:
                        if isinstance(child, list):
                            if len(child) == 4 and isinstance(child[0], str) and child[0] == '$':
                                if child[1] == 'script' and child[3]['type'] == 'application/ld+json':
                                    if child[3]['dangerouslySetInnerHTML']['__html'].startswith('$'):
                                        key = child[3]['dangerouslySetInnerHTML']['__html'][1:]
                                        if key in next_json:
                                            ld_json = next_json[key]
                                    else:
                                        ld_json = child[3]['dangerouslySetInnerHTML']['__html']
                            else:
                                for block in child:
                                    content_html += format_block(block)
        if ld_json:
            if save_debug:
                utils.write_file(ld_json, './debug/debug.json')
            item = {}
            item['id'] = urlsplit(url).path.strip('/').split('/')[-1]
            item['url'] = ld_json['mainEntityOfPage']['@id']
            item['title'] = ld_json['headline']
            dt = datetime.fromisoformat(ld_json['datePublished'])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
            if ld_json.get('dateModified'):
                dt = datetime.fromisoformat(ld_json['dateModified'])
                item['date_modified'] = dt.isoformat()
            if ld_json.get('author'):
                item['authors'] = [{"name": x['name']} for x in ld_json['author']]
                if len(item['authors']) > 0:
                    item['author'] = {
                        "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
                    }
            elif ld_json.get('publisher'):
                item['author'] = {
                    "name": ld_json['publisher']['name']
                }
                item['authors'] = []
                item['authors'].append(item['author'])
            if ld_json.get('articleSection'):
                item['tags'] = []
                item['tags'].append(ld_json['articleSection'])
            if ld_json.get('image'):
                item['image'] = ld_json['image']
            if ld_json.get('description'):
                item['summary'] = ld_json['description']
            if content_html:
                soup = BeautifulSoup(content_html, 'html.parser')
                for el in soup.find_all('div', class_=['px-5', 'prose', 'max-w-site', 'col-span-full']):
                    el.unwrap()
                for el in soup.find_all(class_=['mx-auto', 'mt-5', 'space-y-8', 'shadow-paywall', 'scroll-m-24', 'hidden']):
                    el.decompose()
                for el in soup.select('.grid:has(h2:-soup-contains("More From"))'):
                    el.decompose()
                el = soup.find('h1')
                if el:
                    el.decompose()
                for el in soup.find_all('div', recursive=False):
                    el.unwrap()
                for el in soup.find_all('span', recursive=False):
                    el.decompose()
                item['content_html'] = str(soup)
            return item
        else:
            logger.warning('unable to find article content in ' + url)
            return None

    if save_debug:
        utils.write_file(article_content, './debug/debug.json')

    item = {}
    item['id'] = article_content['id']
    item['url'] = url
    item['title'] = article_content['headline']

    dt = datetime.fromisoformat(article_content['displayDate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if article_content.get('lastCmsUpdateDate'):
        dt = datetime.fromisoformat(article_content['lastCmsUpdateDate'])
        item['date_modified'] = dt.isoformat()

    if article_content.get('authors'):
        item['authors'] = []
        authors = []
        if isinstance(article_content['authors'], str) and article_content['authors'].startswith('$'):
            key = article_content['authors'][1:]
            if key in next_json:
                authors = next_json[key]
        elif isinstance(article_content['authors'], list):
            authors = article_content['authors']
        for it in authors:
            author = {}
            if isinstance(it, str) and it.startswith('$'):
                k = it[1:]
                if k in next_json:
                    author = next_json[k]
            elif isinstance(it, dict):
                author = it
            if author:
                if author.get('byline'):
                    item['authors'].append({"name": author['byline']})
                elif author.get('name'):
                    if author.get('organization'):
                        item['authors'].append({"name": author['name'] + ' (' + author['organization'] + ')'})
                    else:
                        item['authors'].append({"name": author['name']})
        if len(item['authors']) > 0:
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'].replace(',', '&#44;') for x in item['authors']]))
            }
            item['author']['name'] = item['author']['name'].replace('&#44;', ',')
        else:
            del item['authors']

    item['tags'] = []
    if article_content.get('sections'):
        tags = []
        if isinstance(article_content['sections'], str) and article_content['sections'].startswith('$'):
            key = article_content['sections'][1:]
            if key in next_json:
                tags = next_json[key]
        elif isinstance(article_content['sections'], list):
            tags = article_content['sections']
        for it in tags:
            tag = {}
            if isinstance(it, str) and it.startswith('$'):
                k = it[1:]
                if k in next_json:
                    tag = next_json[k]
            elif isinstance(it, dict):
                tag = it
            if tag and 'name' in tag:
                item['tags'].append(tag['name'])
    if article_content.get('tags'):
        tags = []
        if isinstance(article_content['tags'], str) and article_content['tags'].startswith('$'):
            key = article_content['tags'][1:]
            if key in next_json:
                tags = next_json[key]
        elif isinstance(article_content['tags'], list):
            tags = article_content['tags']
        for it in tags:
            tag = {}
            if isinstance(it, str) and it.startswith('$'):
                k = it[1:]
                if k in next_json:
                    tag = next_json[k]
            elif isinstance(it, dict):
                tag = it
            if tag and 'name' in tag:
                item['tags'].append(tag['name'])
    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''

    if article_content['__typename'] == 'Video':
        video_url = next((it for it in next_json[article_content['streams'][1:]] if '/master.m3u8' in it), None)
        if not video_url:
            video_url = next((it for it in next_json[article_content['streams'][1:]] if '/sd.m3u8' in it), None)
            if not video_url:
                video_url = next((it for it in next_json[article_content['streams'][1:]] if '/mobile.m3u8' in it), None)
                if not video_url:
                    video_url = next((it for it in next_json[article_content['streams'][1:]] if '.m3u8' in it), None)
                    if not video_url:
                        video_url = next_json[article_content['streams'][1:]][0]
        if '.m3u8' in video_url:
            item['content_html'] += utils.add_video(video_url, 'application/x-mpegURL', article_content['thumbnail']['url'], article_content['headline'])
        else:
            item['content_html'] += utils.add_video(video_url, 'video/mp4', article_content['thumbnail']['url'], article_content['headline'])
        return item
    
    if article_content.get('dek'):
        item['summary'] = article_content['dek']
        item['content_html'] += '<p><em>' + article_content['dek'] + '</em></p>'

    if article_content.get('leadArt'):
        image = None
        if isinstance(article_content['leadArt'], str) and article_content['leadArt'].startswith('$'):
            key = article_content['leadArt'][1:]
            block = next_json[key]
            if block['__typename'] == 'EmbeddedImage':
                if isinstance(block['image'], str) and block['image'].startswith('$'):
                    k = block['image'][1:]
                    if k in next_json:
                        image = next_json[k]
        elif isinstance(article_content['leadArt'], dict):
            image = article_content['leadArt']['image']
        if image:
            item['image'] = 'https://arc.stimg.co' + urlsplit(image['url']).path + '?w=640'
            if 'hideLeadArt' not in article_content or article_content['hideLeadArt'] == False:
                item['content_html'] += add_image(image, next_json)

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    has_dropcap = False
    body = []
    if isinstance(article_content['body'], str) and article_content['body'].startswith('$'):
        key = article_content['body'][1:]
        if key in next_json:
            body = next_json[key]
    elif isinstance(article_content['body'], list):
        body = article_content['body']
    for it in body:
        if isinstance(it, str) and it.startswith('$'):
            block = next_json[it[1:]]
        elif isinstance(it, dict):
            block = it
        else:
            block = None
        if block:
            if block['__typename'] == 'BodyParagraph':
                if 'dropCap' in block and block['dropCap'] == True:
                    item['content_html'] += '<p class="dropcap">'
                    has_dropcap = True
                else:
                    item['content_html'] += '<p>'
                if block['content'].startswith('$') and block['content'][1:] in next_json:
                    item['content_html'] += next_json[block['content'][1:]]
                else:    
                    item['content_html'] += block['content']
                item['content_html'] += '</p>'
            elif block['__typename'] == 'BodyHeading':
                item['content_html'] += '<h{0}>{1}</h{0}>'.format(block['level'], block['content'])
            elif block['__typename'] == 'BodyImage':
                image = None
                if isinstance(block['image'], str) and block['image'].startswith('$'):
                    key = block['image'][1:]
                    if key in next_json:
                        image = next_json[key]
                elif isinstance(block['image'], dict):
                    image = block['image']
                if image:
                    item['content_html'] += add_image(image, next_json)
            elif block['__typename'] == 'BodyList':
                if block['listType'] == 'UNORDERED':
                    tag = 'ul'
                else:
                    tag = 'ol'
                item['content_html'] += '<{}>'.format(tag)
                for it in next_json[block['listItems'][1:]]:
                    item['content_html'] += '<li>' + it + '</li>'
                item['content_html'] += '</{}>'.format(tag)
            elif block['__typename'] == 'BodyEmbed':
                item['content_html'] += utils.add_embed(block['url'])
            elif block['__typename'] == 'BodyCodeBlock' and '<iframe' in block['content']:
                m = re.search(r'src="([^"]+)"', block['content'])
                item['content_html'] += utils.add_embed(m.group(1))
            else:
                logger.warning('unhandled block type {} in {}'.format(block['__typename'], item['url']))

    if has_dropcap:
        item['content_html'] += '<style>' + config.dropcap_style + '</style>'
    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('.rss2'):
        # https://www2.startribune.com/rss-index/112994779/
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    if len(paths) == 2 and paths[-1].isnumeric():
        # Author
        api_url = 'https://www.startribune.com/api/author-articles?path=' + paths[-1] + '&limit=12'
        key = 'getAuthor'
    else:
        api_url = 'https://www.startribune.com/api/section?path=' + split_url.path + '&limit=12'
        key = 'getSection'
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    n = 0
    feed_items = []
    for article in api_json[key]['content']:
        article_url = 'https://www.startribune.com/{}/{}'.format(article['urlSlug'], article['id'])
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
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
