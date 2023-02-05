import json, math, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, usatoday_sportswire

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000, w=None, h=None):
    split_url = urlsplit(img_src)
    query = split_url.query
    if not query:
        query = '&fit=crop&format=pjpg&auto=webp'
    if not w or not h:
        m = re.search(r'&?height=(\d+)', query)
        if m:
            h = int(m.group(1))
            query = query.replace(m.group(0), '')
        m = re.search(r'&?width=(\d+)', query)
        if m:
            w = int(m.group(1))
            query = query.replace(m.group(0), '')
        if not h or not w:
            w, h = utils.get_image_size(img_src)
        if not w or not h:
            return img_src
    height = math.floor(h*width/w)
    if not query.startswith('&'):
        query = '&' + query
    return '{}://{}{}?width={}&height={}{}'.format(split_url.scheme, split_url.netloc, split_url.path, width, height, query)


def get_image(el):
    if el.name == 'img':
        el_img = el
    else:
        el_img = el.find('img')
    if not el_img:
        return '', ''

    img_src = ''
    if el_img.has_attr('src'):
        img_src = el_img['src']
    elif el_img.has_attr('data-gl-src'):
        img_src = el_img['data-gl-src']
    img_src = resize_image(img_src)

    caption = []
    it = el.find(attrs={"data-c-caption": True})
    if it:
        if it['data-c-caption']:
            caption.append(it['data-c-caption'])
    it = el.find(attrs={"data-c-credit": True})
    if it:
        if it['data-c-credit']:
            caption.append(it['data-c-credit'])

    return img_src, ' | '.join(caption)


def get_gallery_content_old(gallery_soup):
    gallery_html = ''
    for slide in gallery_soup.find_all('slide'):
        img_src = resize_image(slide['original'])
        caption = []
        if slide.get('caption'):
            cap = slide['caption'].replace('&nbsp;', ' ').strip()
            if cap.endswith('<br />'):
                cap = cap[:-6].strip()
            caption.append(cap)
        if slide.get('author'):
            caption.append(slide['author'])
        gallery_html += utils.add_image(img_src, ' | '.join(caption)) + '<br/>'
    return gallery_html


def get_gallery_content(gallery_id, site_code):
    api_url = 'https://api.gannett-cdn.com/thorium/gallery/?apiKey=TGgXAxAcR3ktiGl6cRsHSGsLS6ySi6yz&site-code={}&id={}'.format(site_code, gallery_id)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return ''
    images = api_json['data']['asset']['links']['assets']
    gallery_html = '<h3>{} ({} images)</h3>'.format(api_json['data']['asset']['headline'], len(images))
    for image in images:
        img = next((it for it in image['asset']['crops'] if it['name'] == 'bestCrop'), None)
        img_src = resize_image(img['path'], 1000, img['width'], img['height'])
        captions = []
        if image['asset'].get('caption'):
            captions.append(image['asset']['caption'])
        if image['asset'].get('byline'):
            captions.append(image['asset']['byline'])
        gallery_html += utils.add_image(img_src, ' | '.join(captions)) + '<br/>'
    return gallery_html


def get_content(url, args, site_json, save_debug=False, article_json=None):
    split_url = urlsplit(url)
    base_url = split_url.scheme + '://' + split_url.netloc
    tld = tldextract.extract(url)

    if '/storytelling/' in split_url.path:
        logger.warning('unhandled storytelling content ' + url)
        return None
    elif tld.domain == 'usatoday' and re.search(r'ftw|wire$', tld.subdomain):
        return usatoday_sportswire.get_content(url, args, site_json, save_debug)

    article_html = utils.get_url_html(url, user_agent='googlebot')
    if save_debug:
        utils.write_file(article_html, './debug/debug.html')

    ld_article_json = None
    if article_html:
        soup = BeautifulSoup(article_html, 'html.parser')
        el = soup.find('script', attrs={"type": "application/ld+json"})
        if el:
            ld_json = json.loads(el.string)
            if save_debug:
                utils.write_file(ld_json, './debug/ld.json')
            if isinstance(ld_json, list):
                ld_article_json = next((it for it in ld_json if it['@type'] == 'NewsArticle'), None)
            else:
                if ld_json['@type'] == 'NewsArticle':
                    ld_article_json = ld_json

    if not article_json:
        split_url = urlsplit(url)
        paths = list(filter(None, split_url.path.split('/')))
        article_id = paths[-1]
        m = re.search(r'"siteCode[":\\]+(\w{4})', article_html)
        if not m:
            logger.warning('unable to determine siteCode for ' + url)
            return None
        site_code = m.group(1)
        api_url = 'https://api.gannett-cdn.com/argon/video/{}?apiKey=f6YYPA1hPnB9Y9chky5GOmrZKmaguLVh&site-code={}&url={}'.format(article_id, site_code, url)
        api_json = utils.get_url_json(api_url)
        if not api_json:
            logger.warning('unable to get article json from ' + api_url)
            return None
        article_json = api_json['data']['asset']

    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = article_json['pageURL']['long']
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['publishDate'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {}
    if article_json.get('byline'):
        item['author']['name'] = article_json['byline']
    elif ld_article_json and ld_article_json.get('author'):
        if isinstance(ld_article_json['author'], list):
            authors = []
            for it in ld_article_json['author']:
                authors.append(it['name'])
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        elif isinstance(ld_article_json['author'], dict):
            item['author']['name'] = ld_article_json['author']['name']
        elif isinstance(ld_article_json['author'], str):
            item['author']['name'] = ld_article_json['author']
    else:
        item['author']['name'] = article_json['publication']

    item['tags'] = []
    for it in article_json['tags']:
        item['tags'].append(it['name'])

    if article_json.get('links') and article_json['links'].get('photo') and article_json['links']['photo'].get('crops'):
        image = next((it for it in article_json['links']['photo']['crops'] if it['name'] == '16_9'), None)
        if image:
            item['_image'] = image['path']
    if not item.get('_image') and article_json.get('thumbnail'):
        item['_image'] = article_json['thumbnail']

    if article_json.get('mp4URL'):
        item['_video'] = article_json['mp4URL']

    item['summary'] = article_json['promoBrief']

    soup = BeautifulSoup(article_html, 'html.parser')

    if article_json['type'] == 'video':
        item['content_html'] = utils.add_video(item['_video'], 'video/mp4', item['_image'])
        item['content_html'] += '<p>{}</p>'.format(item['summary'])

    elif article_json['type'] == 'gallery':
        item['content_html'] = get_gallery_content(item['id'], site_code)

    else:
        # article_json['type'] == 'text'
        article = soup.find(class_='gnt_ar_b')
        if not article:
            logger.warning('unable to parse article contents in ' + url)
            return item

        # Ads
        for el in article.find_all(attrs={"aria-label": "advertisement"}):
            el.decompose()

        # Lead image
        el = soup.find(class_='gnt_em__fp')
        if not el:
            el = soup.find('h1', class_=re.compile(r'gnt_\w+_hl'))
            if el:
                el = el.next_sibling
        if el:
            new_el = None
            if el.name == 'figure':
                img_src, caption = get_image(el)
                new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
            elif el.name == 'aside':
                if el.button and el.button.has_attr('data-c-vpdata'):
                    video_json = json.loads(el.button['data-c-vpdata'])
                    if video_json:
                        video_url = video_json['url']
                        if video_url.startswith('/'):
                            video_url = base_url + video_url
                        video = get_content(video_url, {}, site_json, save_debug)
                        if video:
                            new_el = BeautifulSoup(utils.add_video(video['_video'], 'video/mp4', video['_image'], video['summary']), 'html.parser')
                elif el.has_attr('data-c-vt') and el['data-c-vt'] == 'youtube':
                    new_el = BeautifulSoup(utils.add_embed(el.a['href']), 'html.parser')
            if new_el:
                article.insert(0, new_el)
                el.decompose()

        # Images
        for el in article.find_all('figure', class_='gnt_em_img'):
            img_src, caption = get_image(el)
            new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        # Gallery
        for el in article.find_all('a', class_='gnt_em_gl'):
            gallery_url = '{}/content?read&url={}'.format(config.server, quote_plus(base_url + el['href']))
            new_html = '<h3><a href="{}">{}</a></h3>'.format(gallery_url, el['aria-label'])
            img_src, caption = get_image(el)
            if img_src:
                new_html += utils.add_image(img_src, caption, link=gallery_url)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        # Pullquote
        for el in article.find_all(class_='gnt_em_pq'):
            new_el = BeautifulSoup(utils.add_pullquote(el['data-c-pq'], el['data-c-cr']), 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in article.find_all('aside'):
            if el.has_attr('data-gl-method'):
                new_html = ''
                if el['data-gl-method'] == 'loadTwitter':
                    new_html = utils.add_embed(utils.get_twitter_url(el['data-v-id']))
                elif el['data-gl-method'] == 'loadInstagram':
                    new_html = utils.add_embed(el['data-v-src'])
                elif el['data-gl-method'] == 'loadFacebook':
                    new_html = utils.add_embed(el['data-v-src'])
                elif el['data-gl-method'] == 'loadOmny':
                    new_html = utils.add_embed(el['data-v-src'])
                elif el['data-gl-method'] == 'loadAnc':
                    pass
                elif el['data-gl-method'] == 'loadHb64' and el.get('aria-label') and re.search(r'subscribe', el['aria-label'], flags=re.I):
                    pass
                else:
                    logger.warning('unhandled aside data-gl-method {} in {}'.format(el['data-gl-method'], item['url']))
                if new_html:
                    new_el = BeautifulSoup(new_html, 'html.parser')
                    el.insert_after(new_el)
            # Remove these because they are usually ads if not Twitter
            el.decompose()

        # Fix local href links
        for el in article.find_all('a'):
            if el.has_attr('href'):
                href = el.get('href')
            if not href.startswith('http'):
                href = base_url + href
            el.attrs = {}
            el['href'] = href

        # Clear remaining attrs
        article.attrs = {}
        for el in article.find_all(re.compile(r'\b(h\d|li|ol|p|span|ul)\b'), class_=True):
            el.attrs = {}

        item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', str(article))

    if not item.get('_image'):
        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['_image'] = el['content']
        else:
            el = article.find('img')
            if el:
                item['_image'] = el['src']
    return item


def get_feed(url, args, site_json, save_debug):
    split_url = urlsplit(args['url'])
    if 'rssfeeds' in split_url.netloc:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    base_url = split_url.scheme + '://' + split_url.netloc
    tld = tldextract.extract(args['url'])
    if tld.domain == 'usatoday' and tld.subdomain.endswith('wire'):
        return wp_posts.get_feed(url, args, site_json, save_debug)

    page_html = utils.get_url_html(args['url'])
    m = re.search(r'"siteCode[":\\]+(\w{4})', page_html)
    if not m:
        logger.warning('unable to determine siteCode for ' + args['url'])
        return None
    site_code = m.group(1)
    api_url = 'https://api.gannett-cdn.com/argon/encore/?apiKey=f6YYPA1hPnB9Y9chky5GOmrZKmaguLVh&site-code={}&size=10&types=text,gallery,video'.format(site_code)

    m = re.search(r'"sstsPath":"([^"]+)"', page_html)
    if not m:
        logger.warning('unable to find sstsPath in ' + args['url'])
        return None
    paths = m.group(1).split('/')
    if len(paths) == 1:
        if paths[0] != 'home':
            api_url += '&sections={}'.format(paths[0])
    elif len(paths) == 2:
        api_url += '&sections={}&subsections={}'.format(paths[0], paths[1])
    elif len(paths) == 3:
        api_url += '&sections={}&subsections={}&topics={}'.format(paths[0], paths[1], paths[2])
    elif len(paths) == 4:
        api_url += '&sections={}&subsections={}&topics={}&subtopics={}'.format(paths[0], paths[1], paths[2], paths[3])
    else:
        logger.warning('unsupported url feed ' + args['url'])
        return None

    # Need to lookup the tagId
    split_url = urlsplit(args['url'])
    query = parse_qs(split_url.query)
    if query.get('tagIds'):
        api_url += '&tagIds={}'.format(query['tagIds'][0])

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    items = []
    for article in api_json:
        url = article['pageURL']['long']
        if save_debug:
            logger.debug('getting content for ' + url)
        if split_url.netloc in url:
            item = get_content(url, args, site_json, save_debug)
        else:
            item = utils.get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args and n == int(args['max']):
                    break

    feed = utils.init_jsonfeed(args)
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
