import base64, json, math, re, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, usatoday_sportswire, wp_posts

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


def add_video(el_button, base_url, site_json):
    video_html = ''
    if el_button.get('data-c-vpdata'):
        video_json = json.loads(el_button['data-c-vpdata'])
        if video_json:
            poster = video_json['image']['url']
            if poster.startswith('/'):
                poster = base_url + poster
            if video_json.get('title'):
                caption = video_json['title']
            elif video_json.get('headline'):
                caption = video_json['headline']
            else:
                caption = ''
            if video_json.get('hlsURL'):
                video_html = utils.add_video(video_json['hlsURL'], 'application/x-mpegURL', poster, caption)
            elif video_json.get('mp4URL'):
                video_html = utils.add_video(video_json['mp4URL'], 'video/mp4', poster, caption, use_proxy=True)
            elif video_json.get('url'):
                video_url = video_json['url']
                if video_url.startswith('/'):
                    video_url = base_url + video_url
                video_item = get_content(video_url, {"embed": True}, site_json, False)
                if video_item:
                    video_html = video_item['content_html']
    return video_html


def get_gallery_content_old(gallery_soup):
    gallery_html = ''
    for slide in gallery_soup.find_all('slide'):
        img_src = resize_image(slide['original'])
        captions = []
        if slide.get('caption'):
            capption = slide['caption'].replace('&nbsp;', ' ').strip()
            if caption.endswith('<br />'):
                caption = caption[:-6].strip()
            captions.append(caption)
        if slide.get('author'):
            captions.append(slide['author'])
        gallery_html += utils.add_image(img_src, ' | '.join(captions)) + '<div>&nbsp;</div>'
    return gallery_html


def get_gallery_content(item, site_code, embed=False):
    api_url = 'https://api.gannett-cdn.com/thorium/gallery/?apiKey=TGgXAxAcR3ktiGl6cRsHSGsLS6ySi6yz&site-code={}&id={}'.format(site_code, item['id'])
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return ''
    utils.write_file(api_json, './debug/gallery.json')
    images = api_json['data']['asset']['links']['assets']
    item['_gallery'] = []
    gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
    for image in images:
        img = next((it for it in image['asset']['crops'] if it['name'] == 'bestCrop'), None)
        if not img:
            img = next((it for it in image['asset']['crops'] if it['name'] == '16_9'), None)
        thumb = resize_image(img['path'], 600, img['width'], img['height'])
        captions = []
        if image['asset'].get('caption'):
            captions.append(image['asset']['caption'])
        if image['asset'].get('byline'):
            captions.append(image['asset']['byline'])
        caption = ' | '.join(captions)
        item['_gallery'].append({"src": img['path'], "caption": caption, "thumb": thumb})
        gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img['path']) + '</div>'
    gallery_html += '</div>'
    gallery_url = '{}/gallery?url={}'.format(config.server, quote_plus(api_json['data']['asset']['pageURL']['long']))
    if not embed:
        content_html = '<h2><a href="{}" target="_blank">View Photo Gallery</a> ({} images)</h2>'.format(gallery_url, len(images))
        content_html += gallery_html
    else:
        caption = '<a href="{}" target="_blank">View Photo Gallery</a> ({} images): {}'.format(gallery_url, len(images), api_json['data']['asset']['headline'])
        content_html = utils.add_image(item['_gallery'][0]['src'], caption, link=gallery_url)
    return content_html


def get_content(url, args, site_json, save_debug=False, article_json=None):
    split_url = urlsplit(url)
    if split_url.netloc == 'data.usatoday.com':
        return None

    paths = list(filter(None, split_url.path[1:].split('/')))
    base_url = split_url.scheme + '://' + split_url.netloc
    tld = tldextract.extract(url)

    if 'embed' in paths:
        args['embed'] = True

    if 'restricted' in paths or 'offers-reg' in paths:
        # https://www.beaconjournal.com/restricted/?return=https%3A%2F%2Fwww.beaconjournal.com%2Fstory%2Fsports%2Fhigh-school%2Ftrack-field%2F2023%2F05%2F20%2Fohsaa-track-and-field-hudson-ohio-high-school-nordonia-district%2F70226336007%2F
        query = parse_qs(split_url.query)
        return get_content(query['return'][0], args, site_json, save_debug, article_json)

    if 'storytelling' in paths:
        logger.warning('unhandled storytelling content ' + url)
        return None
    # elif tld.domain == 'usatoday' and re.search(r'ftw|wire$', tld.subdomain):
    #     return usatoday_sportswire.get_content(url, args, site_json, save_debug)

    if tld.subdomain and tld.subdomain != 'www':
        article_url = '{}://www.{}.{}{}'.format(split_url.scheme, tld.domain, tld.suffix, split_url.path)
    else:
        article_url = url
    article_html = utils.get_url_html(article_url, user_agent='twitterbot')
    # article_html = utils.get_url_html(article_url, use_curl_cffi=True, use_proxy=True)
    if not article_html:
        return None
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
        if m:
            site_code = m.group(1)
        elif 'site_code' in site_json:
            site_code = site_json['site_code']
        else:
            logger.warning('unable to determine siteCode for ' + url)
            return None
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
    elif article_json.get('publication'):
        item['author']['name'] = article_json['publication']
    elif article_json.get('source'):
        item['author']['name'] = article_json['source']

    item['tags'] = []
    if article_json.get('tags'):
        item['tags'] += [x['name'] for x in article_json['tags']]

    if article_json.get('links') and article_json['links'].get('photo') and article_json['links']['photo'].get('crops'):
        image = next((it for it in article_json['links']['photo']['crops'] if it['name'] == '16_9'), None)
        if image:
            item['image'] = image['path']
    if 'image' not in item and article_json.get('thumbnail'):
        item['image'] = article_json['thumbnail']

    soup = BeautifulSoup(article_html, 'lxml')
    if site_json:
        if site_json and site_json.get('decompose'):
            for it in site_json['decompose']:
                for el in utils.get_soup_elements(it, soup):
                    el.decompose()
        if site_json and site_json.get('unwrap'):
            for it in site_json['unwrap']:
                for el in utils.get_soup_elements(it, soup):
                    el.unwrap()
        if site_json and site_json.get('rename'):
            for it in site_json['rename']:
                for el in utils.get_soup_elements(it, soup):
                    el.name = it['name']

    if 'image' not in item:
        el = soup.find('meta', attrs={"property": "og:image"})
        if el:
            item['image'] = el['content']

    if article_json.get('hlsURL'):
        item['_video'] = article_json['hlsURL']
        item['_video_type'] = 'application/x-mpegURL'
    if article_json.get('mp4URL'):
        if '_video' not in item:
            item['_video'] = article_json['mp4URL']
            item['_video_type'] = 'video/mp4'
        else:
            item['_video_mp4'] = article_json['mp4URL']

    item['summary'] = article_json['promoBrief']

    if article_json['type'] == 'video':
        item['content_html'] = utils.add_video(item['_video'], item['_video_type'], item['image'], item['title'], use_videojs=True)
        if 'embed' not in args and 'summary' in item:
            item['content_html'] += '<p>{}</p>'.format(item['summary'])
        return item

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''

    el = soup.find('h2', class_='gnt_ar_shl')
    if el:
        # Subheadline
        item['content_html'] += '<p><em>{}</em></p>'.format(el.decode_contents())

    if article_json['type'] == 'gallery':
        item['content_html'] += get_gallery_content(item, site_code)
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
        new_el = None
        el = soup.find(class_='gnt_em__fp')
        if not el:
            el = soup.find('h1', class_=re.compile(r'gnt_\w+_hl'))
            if el:
                el = el.next_sibling
        if el:
            if el.name == 'figure':
                img_src, caption = get_image(el)
                if img_src.startswith(':'):
                    img_src = re.sub(r'^[:/]+', r'https://{}/'.format(split_url.netloc), img_src)
                new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
            elif el.name == 'aside':
                if el.button and el.button.has_attr('data-c-vpdata'):
                    new_html = add_video(el.button, base_url, site_json)
                    if new_html:
                        new_el = BeautifulSoup(new_html, 'html.parser')
                    else:
                        logger.warning('unhandled lede video in ' + item['url'])
                elif el.has_attr('data-c-vt') and el['data-c-vt'] == 'youtube':
                    new_el = BeautifulSoup(utils.add_embed(el.a['href']), 'html.parser')
        if new_el:
            article.insert(0, new_el)
            el.decompose()
        elif 'image' in item:
            new_html = utils.add_image(item['image'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            article.insert(0, new_el)

        # Images
        for el in article.find_all('figure', class_='gnt_em_img'):
            img_src, caption = get_image(el)
            if img_src.startswith(':'):
                img_src = re.sub(r'^[:/]+', r'https://{}/'.format(split_url.netloc), img_src)
            new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        # Gallery
        for el in article.find_all('a', class_='gnt_em_gl'):
            caption = ''
            it = el.find('img', class_='ar-lead-image')
            if it:
                img_src = resize_image('{}://{}{}'.format(split_url.scheme, split_url.netloc, it['src']))
            else:
                it = el.find('img', class_='gnt_em_gl_i')
                if it:
                    img_src = resize_image('{}://{}{}'.format(split_url.scheme, split_url.netloc, it['data-gl-src']))
                else:
                    img_src, caption = get_image(el)
            if not caption:
                it = el.find('div', class_='gnt_em_t', attrs={"aria-label": True})
                if it:
                    caption = it['aria-label']
            if caption:
                caption += '<br/>'
            gallery_url = '{}/content?read&url={}'.format(config.server, quote_plus(base_url + el['href']))
            caption += '<a href="{}">{}</a>'.format(gallery_url, el['aria-label'])
            if img_src:
                if img_src.startswith(':'):
                    img_src = re.sub(r'^[:/]+', r'https://{}/'.format(split_url.netloc), img_src)
                img_src = config.server + '/image?url=' + quote_plus(img_src) + '&overlay=gallery'
                new_html = utils.add_image(img_src, caption, link=gallery_url)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unknown gallery image src in ' + item['src'])

        # Pullquote
        for el in article.find_all(class_='gnt_em_pq'):
            new_el = BeautifulSoup(utils.add_pullquote(el['data-c-pq'], el['data-c-cr']), 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in article.find_all('aside'):
            # print(str(el))
            new_html = ''
            if (el.get('aria-label') and re.search(r'advertisement|signup|subscribe', el['aria-label'], flags=re.I)) or (el.get('class') and 'gnt_em_fo__bet-best' in el['class']):
                logger.debug('skipping aside ' + str(el['class']))
                el.decompose()
                continue
            elif 'gnt_ar_b_sp' in el['class']:
                el.decompose()
                continue
            elif 'gnt_em_cp' in el['class'] and el['data-c-cta'] == 'DIG DEEPER':
                # Content package - a list of related links
                el.decompose()
                continue
            elif 'gnt_em_vp__tp' in el['class']:
                if el.button and el.button.get('data-c-vpdata'):
                    new_html = add_video(el.button, base_url, site_json)
            elif 'gnt_em_vp__yt' in el['class']:
                it = el.find(attrs={"data-c-vpattrs": True})
                if it:
                    data_json = json.loads(it['data-c-vpattrs'])
                    if data_json.get('videoId'):
                        new_html = utils.add_embed('https://www.youtube.com/watch?v={}'.format(data_json['videoId']))
            elif 'gnt_em_gd' in el['class'] or 'gnt_em_gm' in el['class']:
                src = ''
                if el.get('data-v-src'):
                    src = el['data-v-src']
                else:
                    it = el.find(attrs={"data-v-src": True})
                    if it:
                        src = it['data-v-src']
                if src:
                    new_html = utils.add_embed(src)
            elif 'gnt_em_pdf' in el['class']:
                it = el.find(attrs={"data-v-pdfurl": True})
                if it:
                    if re.search(r'documentcloud\.org', it['data-v-pdfurl']):
                        new_html = utils.add_embed(it['data-v-pdfurl'])
                    else:
                        new_html = utils.add_embed('https://drive.google.com/viewerng/viewer?url=' + quote_plus(it['data-v-pdfurl']))
            elif 'gnt_em_gm' in el['class']:
                # Google Map
                print(el.iframe)
                new_html = utils.add_embed(el.iframe['src'])
            elif el.has_attr('data-gl-method'):
                if el['data-gl-method'] == 'loadTwitter':
                    new_html = utils.add_embed(utils.get_twitter_url(el['data-v-id']))
                elif el['data-gl-method'] == 'loadInstagram':
                    new_html = utils.add_embed(el['data-v-src'])
                elif el['data-gl-method'] == 'loadFacebook':
                    new_html = utils.add_embed(el['data-v-src'])
                elif el['data-gl-method'] == 'loadOmny':
                    new_html = utils.add_embed(el['data-v-src'])
                elif el['data-gl-method'] == 'loadInfogram':
                    new_html = utils.add_embed('https://infogram.com/' + el['data-v-id'])
                elif el['data-gl-method'] == 'loadHb64' and el.get('data-gl-hb64'):
                    data = base64.b64decode(el['data-gl-hb64']).decode('utf-8')
                    data_soup = BeautifulSoup(data, 'html.parser')
                    utils.write_file(data, './debug/embed.html')
                    if data_soup.iframe:
                        new_html = utils.add_embed(data_soup.iframe['src'])
                    elif data_soup.find(class_='oembed-asset-photo'):
                        captions = []
                        it = data_soup.find(class_='oembed-asset-photo-title')
                        if it:
                            captions.append(it.decode_contents())
                        it = data_soup.find(class_='oembed-asset-photo-caption')
                        if it:
                            captions.append(it.decode_contents())
                        it = data_soup.find(class_='oembed-asset-photo-image')
                        if it:
                            new_html = utils.add_image(it['src'], ' | '.join(captions))
                elif el['data-gl-method'] == 'loadAnc' or el['data-gl-method'] == 'flp':
                    el.decompose()
                    continue
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
            else:
                logger.warning('unhandled aside class {} in {}'.format(el['class'], item['url']))
            el.decompose()

        # Related article links
        for el in article.find_all('a', class_='gnt_ar_b_a', attrs={"data-t-l": re.compile(r'click:')}):
            it = el.find_parent('p', class_='gnt_ar_b_p')
            if it and el.find_previous_sibling('strong', class_='gnt_ar_b_al'):
                it.decompose()

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

        item['content_html'] += re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', str(article))

    if 'image' not in item:
        el = article.find('img')
        if el:
            item['image'] = el['src']
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
