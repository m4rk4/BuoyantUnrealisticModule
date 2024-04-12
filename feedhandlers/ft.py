import base64, json, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    if '/__origami/' in img_src:
        return re.sub(r'width=\d+', 'width={}'.format(width), img_src)
    return 'https://www.ft.com/__origami/service/image/v2/images/raw/{}?source=next&fit=scale-down&width={}'.format(quote_plus(img_src), width)


def add_image(image_el):
    el = image_el.find('img')
    if el:
        img_src = resize_image(el['src'])
    else:
        logger.warning('unable to determine image src')
        return ''
    el = image_el.find('figcaption')
    if el:
        caption = el.decode_contents().strip()
        if not caption.startswith('©'):
            caption = caption.replace('©', '| ©')
    else:
        caption = ''
    return utils.add_image(img_src, caption)


def get_content(url, args, site_json, save_debug=False):
    if url.startswith('://'):
        url = url.replace('://', 'https://www.ft.com')

    if '/reports/' in url:
        # skip
        return None

    # headers = {
    #     "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    #     "accept-encoding": "gzip, deflate, br",
    #     "accept-language": "en-US,en;q=0.9,de;q=0.8",
    #     "host": "www.ft.com",
    #     "referrer": "https://www.google.com/",
    #     "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"101\", \"Microsoft Edge\";v=\"101\"",
    #     "sec-ch-ua-mobile": "?0",
    #     "sec-ch-ua-platform": "\"Windows\"",
    #     "sec-fetch-dest": "document",
    #     "sec-fetch-mode": "navigate",
    #     "sec-fetch-site": "cross-site",
    #     "sec-fetch-user": "?1",
    #     "upgrade-insecure-requests": "1",
    #     "user-agent": "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36 Edg/101.0.1210.53"
    # }
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "accept-language": "en-US,en;q=0.9",
        "referrer": "https://www.google.com/",
        "sec-ch-ua": "\"Not?A_Brand\";v=\"8\", \"Chromium\";v=\"108\", \"Microsoft Edge\";v=\"108\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36 Edg/108.0.1462.42"
    }
    article_html = utils.get_url_html(url, headers=headers)
    if not article_html:
        return None
    if save_debug:
        utils.write_file(article_html, './debug/debug.html')

    ld_json = None
    soup = BeautifulSoup(article_html, 'html.parser')
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        try:
            ld_json = json.loads(el.string)
            if re.search(r'Article|VideoObject', ld_json['@type']):
                break
        except:
            logger.warning('unable to load ld+json data in ' + url)
        ld_json = None

    if not ld_json:
        # article_html = utils.get_url_html(url, user_agent='googlecache')
        article_html = utils.get_bing_cache(url)
        if article_html:
            soup = BeautifulSoup(article_html, 'html.parser')
        for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
            try:
                ld_json = json.loads(el.string)
                if re.search(r'NewsArticle|VideoObject', ld_json['@type']):
                    break
            except:
                logger.warning('unable to load ld+json data in ' + url)
            ld_json = None

    if not ld_json:
        el = soup.find('script', id='page-kit-app-context')
        if el:
            context_json = json.loads(el.string)
            if context_json['contentType'] == 'podcast':
                logger.warning('podcast content')
                return None
        logger.warning('unable to find ld+json data in ' + url)
        return None

    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    item = {}
    item['id'] = url

    if ld_json.get('mainEntityofPage'):
        item['url'] = ld_json['mainEntityofPage']
    elif ld_json.get('url'):
        item['url'] = ld_json['url']
    else:
        item['url'] = url

    if ld_json.get('headline'):
        item['title'] = ld_json['headline']
    elif ld_json.get('name'):
        item['title'] = ld_json['name']

    dt = datetime.fromisoformat(ld_json['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if ld_json.get('dateModified'):
        dt = datetime.fromisoformat(ld_json['dateModified'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    item['author'] = {}
    if ld_json.get('author'):
        if isinstance(ld_json['author'], dict):
            if ld_json.get('author') and ld_json['author'].get('name'):
                item['author']['name'] = ld_json['author']['name']
        elif isinstance(ld_json['author'], list):
            authors = []
            for author in ld_json['author']:
                authors.append(author['name'])
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif ld_json.get('publisher') and ld_json['publisher'].get('name'):
        item['author']['name'] = ld_json['publisher']['name']
    if not item['author'].get('name') or item['author']['name'] == 'Staff Writer':
        el = soup.find(attrs={"data-trackable": "byline"})
        if el:
            item['author']['name'] = el.get_text()
    if not item['author'].get('name'):
        if ld_json.get('publisher'):
            item['author']['name'] = ld_json['publisher']['name']
        else:
            item['author']['name'] = urlsplit(url).netloc

    if ld_json.get('image'):
        if isinstance(ld_json['image'], dict):
            item['_image'] = ld_json['image']['url']
        elif isinstance(ld_json['image'], str):
            item['_image'] = ld_json['image']

    if ld_json.get('description'):
        item['summary'] = ld_json['description']

    el = soup.find('meta', attrs={"name": "keywords"})
    if el:
        item['tags'] = list(map(str.strip, el['content'].split(',')))
    else:
        item['tags'] = []
        for el in soup.find_all('a', class_='concept-list__concept'):
            item['tags'].append(el.get_text().strip())
        if not item.get('tags'):
            del item['tags']

    if ld_json['@type'] == 'VideoObject':
        item['_video'] = ld_json['contentUrl']
        caption = '<a href="{}">{}</a>. {}'.format(item['url'], item['title'], item['summary'])
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', resize_image(ld_json['thumbnailUrl']), caption)
        if 'embed' not in args:
            el = soup.find(id='description')
            if el and el.p:
                item['content_html'] += str(el.p)
            el = soup.find(id='transcript')
            if el:
                item['content_html'] += el.decode_contents()
        return item

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;"><a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a><div style="margin-left:8px; margin-right:8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(item['url'], item['_image'], urlsplit(item['url']).netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item


    if 'asia.nikkei.com' in item['url']:
        body_url = 'https://asia.nikkei.com/__service/v1/piano/article_access/' + base64.b64encode(urlsplit(url).path.encode()).decode()
        body_json = utils.get_url_json(body_url)
        if body_json:
            item['content_html'] = ''
            if ld_json.get('alternativeHeadline'):
                item['content_html'] += '<p><em>{}</em></p>'.format(ld_json['alternativeHeadline'])
            el = soup.find(attrs={"data-trackable": "image-main"})
            if el:
                img_src = resize_image(el.img['full'])
                it = el.find_next_sibling()
                if it and it.get('class') and 'article__caption' in it['class']:
                    caption = it.decode_contents()
                else:
                    caption = ''
                item['content_html'] += utils.add_image(img_src, caption)
            if save_debug:
                utils.write_file(body_json, './debug/content.json')
            body = BeautifulSoup(body_json['body'], 'html.parser')
            for el in body.find_all(class_='o-ads'):
                el.decompose()
            for el in body.find_all(id='AdAsia'):
                el.decompose()
            for el in body.find_all(class_='ez-embed-type-image'):
                img_src = resize_image(el.img['full'])
                it = el.find(class_='article__caption')
                if it:
                    caption = it.decode_contents()
                else:
                    caption = ''
                new_html = utils.add_image(img_src, caption)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            if body.contents[0].name == 'div' and body.contents[0].get('class') and 'ezrichtext-field' in body.contents[0]['class']:
                body.contents[0].unwrap()
            item['content_html'] += str(body)
        else:
            logger.warning('unable to get body content for ' + item['url'])

    elif ld_json.get('articleBody'):
        article_body = soup.find(['article', 'div'], attrs={"data-attribute": "article-content-body"})
        for el in article_body.find_all('div', class_='o-ads'):
            el.decompose()

        for el in article_body.find_all('aside'):
            el.decompose()

        for el in article_body.find_all(class_='n-content-layout'):
            #print(el.get('data-layout-name'))
            if el.get('data-layout-name') == 'card':
                # Skip newsletter signups
                if not el.find('a', href=re.compile('https://ep\.ft\.com/newsletters/subscribe')):
                    img = el.find('img')
                    if img:
                        new_html = '<table><tr><td style="vertical-align:top;"><img src="{}" style="width:240px;"/></td><td style="vertical-align:top;">'.format(resize_image(img['src'], 240))
                    else:
                        new_html = '<blockquote>'
                    it = el.find('h2')
                    if it:
                        new_html += '<strong>{}</strong><br/>'.format(it.get_text())
                    for it in el.find_all('p'):
                        new_html += it.decode_contents() + '<br/><br/>'
                    new_html = new_html[:-10]
                    if img:
                        new_html += '</td></tr></table>'
                    else:
                        new_html = '</blockquote>'
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_before(new_el)
            else:
                for it in el.find_all(class_=['n-content-image', 'n-content-picture']):
                    new_html = add_image(it)
                    if new_html:
                        new_el = BeautifulSoup(new_html, 'html.parser')
                        el.insert_before(new_el)
            el.decompose()

        for el in article_body.find_all(class_=['n-content-image', 'n-content-picture']):
            new_html = add_image(el)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_before(new_el)
                el.decompose()

        for el in article_body.find_all(class_='n-content-video'):
            if 'n-content-video--internal' in el['class']:
                video_item = get_content(el.a['href'], {"embed": True}, site_json, False)
                if video_item:
                    new_el = BeautifulSoup(video_item['content_html'], 'html.parser')
                    el.insert_before(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled n-content-video--internal in ' + item['url'])
            elif 'n-content-video--youtube' in el['class']:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_before(new_el)
                    el.decompose()
                else:
                    logger.warning('unhandled n-content-video--youtube in ' + item['url'])
            else:
                logger.warning('unhandled n-content-video in ' + item['url'])

        for el in article_body.find_all(class_='n-content-tweet'):
            it = el.find_all('a')
            new_html = utils.add_embed(it[-1]['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in article_body.find_all(class_='n-content-pullquote'):
            it = el.find(class_='n-content-pullquote__footer')
            if it:
                author = it.get_text()
                it.decompose()
            else:
                author = ''
            it = el.find(class_='n-content-pullquote__content')
            if it:
                new_html = utils.add_pullquote(it.decode_contents().strip(), author)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_before(new_el)
                el.decompose()

        for el in article_body.find_all(class_=re.compile('n-content-heading')):
            el.attrs = {}

        for el in article_body.find_all('experimental'):
            el.unwrap()

        item['content_html'] = ''
        if article_body.find().name != 'figure':
            el = soup.find(class_='o-topper__standfirst')
            if el:
                item['content_html'] += '<p><em>' + el.decode_contents() + '</em></p>'
            el = soup.find(class_='o-topper__visual')
            if not el:
                el = soup.find(class_='main-image')
            if el and len(el.contents) > 0:
                item['content_html'] += add_image(el)
            elif item.get('_image'):
                item['content_html'] += utils.add_image(resize_image(item['_image']))

        item['content_html'] += article_body.decode_contents()

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
