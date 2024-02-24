import html, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from urllib.parse import urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content_item(article_json, args, site_json, save_debug):
    # https://www.bizjournals.com/api/content/leadership
    item = {}
    item['id'] = article_json['article_id']
    item['url'] = article_json['url']
    item['title'] = article_json['headline']

    tz_loc = pytz.timezone(('US/Eastern'))
    dt_loc = datetime.fromisoformat(article_json['published_at'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_loc = datetime.fromisoformat(article_json['updated_at'])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    # TODO: find author name given author_id

    if article_json.get('excerpt'):
        item['summary'] = article_json['excerpt']

    item['content_html'] = ''
    if article_json.get('image_data'):
        item['_image'] = article_json['image_data']['sizes']['full']['source_url']
        if article_json['image_data'].get('caption'):
            caption = article_json['image_data']['caption']
        else:
            caption = ''
        item['content_html'] += utils.add_image(item['_image'], caption)

    item['content_html'] += article_json['content']
    return item


def get_html_content(page_soup, url, args, site_json, save_debug):
    meta = {}
    for el in page_soup.find_all('meta'):
        if not el.get('content'):
            continue
        if el.get('property'):
            key = el['property']
        elif el.get('name'):
            key = el['name']
        else:
            continue
        if meta.get(key):
            if isinstance(meta[key], str):
                if meta[key] != el['content']:
                    val = meta[key]
                    meta[key] = []
                    meta[key].append(val)
            if el['content'] not in meta[key]:
                meta[key].append(el['content'])
        else:
            meta[key] = el['content']
    if save_debug:
        utils.write_file(meta, './debug/debug.json')

    params = json.loads(meta['gpt:params'])

    item = {}
    item['id'] = params['pageid']
    item['url'] = meta['og:url']
    if meta.get('sailthru.title'):
        item['title'] = meta['sailthru.title']
    else:
        item['title'] = meta['og:title']

    dt = datetime.fromisoformat(meta['date']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    item['author'] = {"name": params['reporter']}

    if meta.get('news_keywords'):
        item['tags'] = [it.strip() for it in meta['news_keywords'].split(',')]
    elif meta.get('category'):
        item['tags'] = [it.strip() for it in meta['category'].split(',')]

    if meta.get('og:image'):
        item['_image'] = meta['og:image']

    if meta.get('og:description'):
        item['_image'] = meta['og:description']

    item['content_html'] = ''
    el = page_soup.find(id='featuredMedia')
    if el:
        if 'media-content--image' in el['class']:
            it = el.find('img')
            if it:
                if it.get('srcset'):
                    img_src = utils.image_from_srcset(it['srcset'], 1200)
                else:
                    img_src = it['src']
                it = el.find(class_='media-content__caption')
                if it:
                    caption = it.decode_contents()
                else:
                    caption = ''
                item['content_html'] += utils.add_image(img_src, caption)
        else:
            logger.warning('unhandled featuredMedia content in ' + url)
    else:
        el = page_soup.find(class_='article__media article__media--before-column')
        if el:
            it = el.find('img')
            if it:
                if it.get('srcset'):
                    img_src = utils.image_from_srcset(it['srcset'], 1200)
                else:
                    img_src = it['src']
                captions = []
                it = el.find(class_='article__image-byline')
                if it:
                    if it.get_text().strip():
                        captions.append(it.get_text().strip())
                    it.decompose()
                it = el.find(class_='article__image-caption')
                if it and it.get_text().strip():
                    captions.insert(0, it.get_text().strip())
                item['content_html'] += utils.add_image(img_src, ' | '.join(captions))

    body = page_soup.find(class_=['article-content-items', 'article__content'])
    if body:
        for el in body.find_all(['cxense-paywall', 'cxense-incontent']):
            el.decompose()

        for el in body.find_all(class_='ad-container'):
            el.decompose()

        for el in body.find_all('h5'):
            el.name = 'h3'

        for el in body.find_all('b', class_='corrections'):
            el.name = 'p'
            el['style'] = 'font-weight:bold;'

        for el in body.find_all(class_='media-content'):
            new_html = ''
            if 'media-content--image' in el['class']:
                it = el.find('img')
                if it:
                    if it.get('srcset'):
                        img_src = utils.image_from_srcset(it['srcset'], 1200)
                    else:
                        img_src = it['src']
                    it = el.find(class_='media-content__caption')
                    if it:
                        caption = it.decode_contents()
                    else:
                        caption = ''
                    new_html = utils.add_image(img_src, caption)
            elif 'media-content--gallery' in el['class']:
                it = el.find(class_='module-heading-title')
                if it:
                    new_html += '<h3>Gallery: ' + it.get_text() + '</h3>'
                for it in el.find_all(class_='carousel-item'):
                    img = it.find('img')
                    if img:
                        if img.get('srcset'):
                            img_src = utils.image_from_srcset(img['srcset'], 1200)
                        else:
                            img_src = img['src']
                        captions = []
                        caption = it.find(class_='media-content__caption')
                        if caption:
                            captions.append(caption.decode_contents())
                        caption = it.find(class_='media-content__credit')
                        if caption:
                            captions.append(caption.decode_contents())
                        new_html += utils.add_image(img_src, ' | '.join(captions))
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                it = el.find_parent()
                if it and it.get('class') and 'article-content-item' in it['class']:
                    it.insert_after(new_el)
                    it.decompose()
                else:
                    el.insert_after(new_el)
                    el.decompose()
            else:
                logger.warning('unhandled media-content in ' + url)

        for el in body.find_all(class_='article-content-item'):
            el.attrs = {}

        item['content_html'] += body.decode_contents()

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_page_soup(url, site_json):
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "cookie": site_json['cookie'],
        "pragma": "no-cache",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"117\", \"Not;A=Brand\";v=\"8\", \"Chromium\";v=\"117\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.60"
    }
    page_html = utils.get_url_html(url, headers)
    utils.write_file(page_html, './debug/debug.html')
    page_soup = BeautifulSoup(page_html, 'lxml')
    # if page_soup.find('script', src=re.compile(r'_Incapsula_Resource')):
    if page_soup.find('script', id='__NUXT_DATA__') or page_soup.find(class_=['article-content-items', 'article__content']):
        return page_soup

    logger.warning('unable to load page. trying to update incap cookie...')
    with sync_playwright() as playwright:
        engine = playwright.chromium
        browser = engine.launch()
        context = browser.new_context()
        page = context.new_page()
        page.goto('https://www.bizjournals.com')
        cookies = context.cookies()
        browser.close()

    cookie = ''
    for it in cookies:
        if it['name'].startswith('visid_incap') or it['name'].startswith('incap_ses'):
            cookie += '{}={}; '.format(it['name'], it['value'])
    if not cookie:
        logger.warning('unable to get new incap cookie for ' + url)
        return None

    site_json['cookie'] = cookie.strip()
    headers['cookie'] = site_json['cookie']
    logger.debug('updating bizjournals.com incap cookie')
    utils.update_sites(url, site_json)

    page_html = utils.get_url_html(url, headers)
    page_soup = BeautifulSoup(page_html, 'lxml')
    if page_soup.find('script', id='__NUXT_DATA__') or page_soup.find(class_=['article-content-items', 'article__content']):
        return page_soup

    logger.warning('still unable to load page contents ' + url)
    return None


def get_content(url, args, site_json, save_debug=False):
    page_soup = get_page_soup(utils.clean_url(url) + '?page=all', site_json)
    if not page_soup:
        return None
    if save_debug:
        utils.write_file(str(page_soup), './debug/debug.html')

    if '/inno/' in url or '/bizwomen/' in url or '/profiles-strategies/' in url:
        return get_html_content(page_soup, url, args, site_json, save_debug)

    el = page_soup.find('script', id='__NUXT_DATA__')
    if el:
        nuxt_data = json.loads(el.string)
    else:
        logger.warning('unable to find __NUXT_DATA__ in ' + url)
        return None

    #     logger.debug('updating cookies...')
    #     #el = page_soup.find('script', src=re.compile(r'_Incapsula_Resource'))
    #     with sync_playwright() as playwright:
    #         engine = playwright.chromium
    #         browser = engine.launch()
    #         context = browser.new_context()
    #         page = context.new_page()
    #         page.goto('https://www.bizjournals.com')
    #         cookies = context.cookies()
    #         browser.close()
    #     cookie = ''
    #     for it in cookies:
    #         if it['name'].startswith('visid_incap') or it['name'].startswith('incap_ses'):
    #             cookie += '{}={}; '.format(it['name'], it['value'])
    #     if not cookie:
    #         logger.warning('unable to get new incap cookies for ' + url)
    #         return None
    #     site_json['cookie'] = cookie.strip()
    #     logger.debug('updating bizjournals.com cookies')
    #     utils.update_sites(url, site_json)
    #     page_html = get_page_html(url, site_json)
    #     if not page_html:
    #         return None
    #     if save_debug:
    #         utils.write_file(page_html, './debug/debug.html')
    #     page_soup = BeautifulSoup(page_html, 'lxml')
    #     el = page_soup.find('script', id='__NUXT_DATA__')
    #     if el:
    #         nuxt_data = json.loads(el.string)
    #     else:
    #         logger.warning('unable to find __NUXT_DATA__ in ' + url)
    #         nuxt_data = None
    #
    # if not nuxt_data:
    #     return None

    if save_debug:
        utils.write_file(nuxt_data, './debug/debug.json')

    article = None
    for data in nuxt_data:
        if isinstance(data, dict) and data.get('article'):
            article = nuxt_data[data['article']]
            break

    if not article:
        logger.warning('unable to find NUXT_DATA article content in ' + url)
        return None

    item = {}
    item['id'] = nuxt_data[article['id']]
    item['url'] = nuxt_data[article['canonicalUrl']]
    item['title'] = nuxt_data[article['title']]

    tz_loc = None
    for data in nuxt_data:
        if isinstance(data, dict) and data.get('timezone'):
            tz_loc = pytz.timezone(nuxt_data[data['timezone']])
            break
    dt_loc = datetime.fromisoformat(nuxt_data[article['published_at']])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt_loc = datetime.fromisoformat(nuxt_data[article['updated_at']])
    dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt.isoformat()

    authors = []
    for i in nuxt_data[article['authors']]:
        author = nuxt_data[i]
        authors.append(nuxt_data[author['name']])
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['content_html'] = ''
    gallery = ''

    header = nuxt_data[article['header']]
    if header.get('subhead') and nuxt_data[header['subhead']]:
        item['content_html'] += '<p><em>{}</em></p>'.format(nuxt_data[header['subhead']])

    def add_media_image(media):
        nonlocal nuxt_data
        img_src = nuxt_data[media['url']]
        captions = []
        if media.get('caption'):
            captions.append(nuxt_data[media['caption']])
        if media.get('byline'):
            captions.append(nuxt_data[media['byline']])
        return utils.add_image(img_src, ' | '.join(captions))

    if article.get('featuredMedia'):
        media = nuxt_data[article['featuredMedia']]
        if media:
            item['_image'] = nuxt_data[media['url']]
            item['content_html'] += add_media_image(media)
            if media.get('media') and isinstance(nuxt_data[media['media']], list):
                # Slideshow
                for i in nuxt_data[media['media']]:
                    gallery += add_media_image(nuxt_data[i])

    if article.get('audio'):
        media = nuxt_data[article['audio']]
        if media and media.get('full'):
            media = nuxt_data[media['full']]
            media = nuxt_data[media['voices']]
            media = nuxt_data[media[0]]
            item['_audio'] = 'https://audiop.bizjournals.com' + nuxt_data[media['url']]
            attachment = {}
            attachment['url'] = item['_audio']
            attachment['mime_type'] = 'audio/mpeg'
            item['attachments'] = []
            item['attachments'].append(attachment)
            duration = utils.calc_duration(nuxt_data[media['duration']])
            item['content_html'] += '<div>&nbsp;</div><div style="display:flex; align-items:center;"><a href="{0}"><img src="{1}/static/play_button-48x48.png"/></a><span style="padding-left:8px;"><a href="{0}">Listen to this article ({2})</a></span></div>'.format(item['_audio'], config.server, duration)

    if article.get('schemaOrg'):
        schema = nuxt_data[article['schemaOrg']]
        if schema.get('description'):
            item['summary'] = nuxt_data[schema['description']]
        if schema.get('keywords'):
            item['tags'] = [it.strip() for it in nuxt_data[schema['keywords']].split(',')]

    gal = 0
    for c in nuxt_data[article['content']]:
        content = nuxt_data[c]
        if content.get('type'):
            if nuxt_data[content['type']] == 'paragraph':
                item['content_html'] += '<p>' + nuxt_data[content['html']] + '</p>'
            elif nuxt_data[content['type']] == 'header':
                item['content_html'] += '<h2>' + nuxt_data[content['html']] + '</h2>'
            elif nuxt_data[content['type']] == 'list':
                item['content_html'] += nuxt_data[content['html']]
            elif nuxt_data[content['type']] == 'image':
                data = nuxt_data[content['data']]
                if nuxt_data[data['type']] == 'media':
                    ord = nuxt_data[data['ord']]
                    for i in nuxt_data[article['media']]:
                        media = nuxt_data[i]
                        if nuxt_data[media['ord']] == ord:
                            item['content_html'] += add_media_image(media)
                else:
                    logger.warning('unhandled image type {} in {}'.format(nuxt_data[data['type']], item['url']))
            elif nuxt_data[content['type']] == 'gallery':
                data = nuxt_data[content['data']]
                id = nuxt_data[data['id']]
                # gallery = utils.get_url_json('https://www.bizjournals.com/api/content/gallery/' + id)
                for i in nuxt_data[article['gallery']]:
                    media = nuxt_data[i]
                    if nuxt_data[media['id']] == id:
                        for i in nuxt_data[media['media']]:
                            item['content_html'] += add_media_image(nuxt_data[i])
            elif nuxt_data[content['type']] == 'embed':
                if nuxt_data[content['html']].startswith('<iframe'):
                    m = re.search(r'src="([^"]+)"', nuxt_data[content['html']])
                    item['content_html'] += utils.add_embed(m.group(1))
                elif 'instagram-media' in nuxt_data[content['html']]:
                    m = re.search(r'data-instgrm-permalink="([^"]+)"', nuxt_data[content['html']])
                    item['content_html'] += utils.add_embed(m.group(1))
                elif 'infogram-embed' in nuxt_data[content['html']]:
                    m = re.search(r'data-id="([^"]+)"', nuxt_data[content['html']])
                    item['content_html'] += utils.add_embed('https://infogram.com/' + m.group(1))
                elif 'https://trust.bizjournals.com/membership' in nuxt_data[content['html']]:
                    pass
                else:
                    logger.warning('unhandled embed in ' + item['url'])
            elif nuxt_data[content['type']] == 'infographic':
                data = nuxt_data[content['data']]
                if nuxt_data[data['type']] == 'media':
                    ord = nuxt_data[data['ord']]
                    for i in nuxt_data[article['media']]:
                        media = nuxt_data[i]
                        if nuxt_data[media['ord']] == ord:
                            item['content_html'] += add_media_image(media)
            elif nuxt_data[content['type']] == 'blockquote':
                if not re.search(r'Trending:|Read more:', nuxt_data[content['html']]):
                    item['content_html'] += utils.add_blockquote(nuxt_data[content['html']])
            elif nuxt_data[content['type']] == 'horizontal_line':
                item['content_html'] += '<hr/>'
            elif nuxt_data[content['type']] == 'top25list':
                data = nuxt_data[content['data']]
                id = nuxt_data[data['id']]
                for i in nuxt_data[article['lists']]:
                    media = nuxt_data[i]
                    item['content_html'] += '<div>&nbsp;</div><div><strong>The List</strong></div><div style="font-size:1.2em; font-weight:bold;"><a href="{}">{}</a></div><div><small>Ranked by: {}</small></div>'.format(nuxt_data[media['url']], nuxt_data[media['headline']], nuxt_data[media['ranked_by_label']])
                    item['content_html'] += '<table style="width:100%; border-collapse:collapse;">'
                    for n, r in enumerate(nuxt_data[media['listItems']]):
                        if n % 2 == 0:
                            item['content_html'] += '<tr style="line-height:2em; background-color:#e7e7e7; border:1px solid #e7e7e7;">'
                        else:
                            item['content_html'] += '<tr style="line-height:2em; border:1px solid #e7e7e7;">'
                        if n == 0:
                            c = len(nuxt_data[r])
                            for d in nuxt_data[r]:
                                item['content_html'] += '<th style="text-align:left; padding:0 8px 0 8px;">' + nuxt_data[d] + '</th>'
                        else:
                            for d in nuxt_data[r]:
                                item['content_html'] += '<td style="text-align:left; padding:0 8px 0 8px;">' + nuxt_data[d] + '</td>'
                        item['content_html'] += '</tr>'
                    item['content_html'] += '<tr style="line-height:2em; background-color:#aa2224;"><td colspan="{}" style="padding:0 8px 0 8px;"><a href="{}" style="color:white; text-decoration:none;">View this list</a></td>'.format(c, nuxt_data[media['url']])
                    item['content_html'] += '</table>'
                    break
            else:
                logger.warning('unhandled content type {} in {}'.format(nuxt_data[content['type']], item['url']))

    if gallery:
        item['content_html'] += '<h2>Gallery</h2>' + gallery

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if 'rss.bizjournals.com' in url:
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    bizjournals = utils.get_url_json('https://www.bizjournals.com/api/market/bizjournals')
    market = next((it for it in bizjournals['markets'] if it['market_code'] == paths[0]), None)
    if not market:
        market = next((it for it in bizjournals['markets'] if it['market_code'] == 'bizjournals'), None)

    if len(paths) == 0:
        api_url = 'https://content.bizjournals.com/api/v1/page/article/most-recent?market=bizjournals&channel=0&limit=10'
        feed_title = 'The Business Journals'
    elif 'bio' in paths:
        i = paths.index('bio')
        api_url = 'https://content.bizjournals.com/api/v1/page/article/most-recent?author=' + paths[i + 1]
        feed_title = '{} - {} Business Journals'.format(paths[i + 2].replace('+', ' '), market['label'])
    elif 'news' in paths:
        i = paths.index('news')
        if len(paths[i:]) == 1:
            channel = {
                "id": 0,
                "name": "News"
            }
        else:
            channel = next((it for it in bizjournals['channels'] if (it['type'] == 'channel' and it['code'] == paths[i+1])), None)
            if not channel:
                logger.warning('unknown channel for feed ' + url)
                return None
        topic = ''
        if len(paths[i:]) > 2:
            # Get topic id
            page_soup = get_page_soup(url, site_json)
            if not page_soup:
                return None
            el = page_soup.find('script', string=re.compile(r'aaData'))
            if el:
                i = el.string.find('{')
                j = el.string.rfind('}') + 1
                aa_data = json.loads(el.string[i:j])
                if aa_data.get('contentId') and int(aa_data['contentId']) != channel['id']:
                    topic = '&topic=' + aa_data['contentId']
        api_url = 'https://content.bizjournals.com/api/v1/news?market={}&channel={}{}&limit=10'.format(market['market_code'], channel['id'], topic)
        feed_title = '{} | {} Business Journal'.format(channel['name'], market['label'])
    elif 'inno' in paths:
        channel = None
        # TODO

    print(api_url)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    n = 0
    feed_items = []
    for article in api_json['items']:
        # if article.get('sponsor'):
        #     continue
        if isinstance(article['url'], str):
            article_url = article['url']
        elif isinstance(article['url'], list):
            article_url = article['url'][0]
            for it in article['url']:
                if url in it:
                    article_url = it
                    break
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
    feed['title'] = feed_title
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
