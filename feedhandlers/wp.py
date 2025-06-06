import copy, html, json, pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, urlsplit

import config, utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False, module_format_content=None):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if len(paths) > 0 and paths[-1] == 'embed':
        args['embed'] = True
        del paths[-1]
        page_url = '{}://{}/{}'.format(split_url.scheme, split_url.netloc, '/'.join(paths))
    else:
        page_url = url
    base_url = '{}://{}'.format(split_url.scheme, split_url.netloc)

    page_html = utils.get_url_html(page_url, site_json=site_json)
    if not page_html:
        return None

    if 'html_encode' in site_json:
        page_html = page_html.encode(site_json['html_encode']).decode('utf-8')

    if split_url.netloc == 'www.jpost.com':
        page_html = re.sub(r'<section class=["\']fake-br-for-article-body["\']></section>', '</p>', page_html)

    soup = BeautifulSoup(page_html, 'html.parser')
    if save_debug:
        utils.write_file(soup.prettify(), './debug/page.html')

    meta = {}
    for el in soup.find_all('meta'):
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
        utils.write_file(meta, './debug/meta.json')

    parsley_page = None
    if 'parsely-page' in meta:
        try:
            parsley_page = json.loads(meta['parsely-page'])
        except:
            pass

    parsley_meta = None
    if 'parsely-metadata' in meta:
        try:
            parsley_meta = json.loads(meta['parsely-metadata'])
        except:
            pass

    ld_json = []
    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        try:
            if 'ksl.com' in url:
                ld = json.loads(el.string.replace('"" ', '","'))
            else:
                ld = json.loads(el.string)
            if isinstance(ld, list):
                for it in ld:
                    if it.get('@graph'):
                        ld_json += it['@graph'].copy()
                    elif it.get('@type'):
                        ld_json.append(it)
            elif isinstance(ld, dict):
                if ld.get('@graph'):
                    ld_json += ld['@graph'].copy()
                elif ld.get('@type'):
                    ld_json.append(ld)
        except:
            logger.warning('unable to convert ld+json in ' + page_url)
            pass
    if save_debug:
        utils.write_file(ld_json, './debug/debug.json')

    article_json = None
    ld_page = None
    ld_article = None
    ld_people = []
    ld_images = []
    for ld in ld_json:
        if isinstance(ld, dict):
            it = ld
            if not it.get('@type'):
                continue
            if isinstance(it['@type'], str):
                if it['@type'] == 'WebPage':
                    ld_page = it
                elif not article_json and 'Article' in it['@type']:
                    ld_article = it
                elif not article_json and it['@type'] == 'Product' and it.get('Review'):
                    ld_article = it['Review']
                elif it['@type'] == 'Person':
                    ld_people.append(it)
                elif it['@type'] == 'ImageObject':
                    ld_images.append(it)
            elif isinstance(it['@type'], list):
                if 'WebPage' in it['@type']:
                    ld_page = it
                elif not article_json and re.search(r'Article', '|'.join(it['@type'])):
                    article_json = it
                    ld_article = it
        elif isinstance(ld, list):
            for it in ld:
                if not it.get('@type'):
                    continue
                if isinstance(it['@type'], str):
                    if it['@type'] == 'WebPage':
                        ld_page = it
                    elif not article_json and 'Article' in it['@type']:
                        ld_article = it
                    elif not article_json and it['@type'] == 'Product' and it.get('Review'):
                        ld_article = it['Review']
                    elif it['@type'] == 'Person':
                        ld_people.append(it)
                    elif it['@type'] == 'ImageObject':
                        ld_images.append(it)
                elif isinstance(it['@type'], list):
                    if 'WebPage' in it['@type']:
                        ld_page = it
                    elif not article_json and re.search(r'Article', '|'.join(it['@type'])):
                        article_json = it

    if ld_article:
        article_json = ld_article
    elif ld_page:
        article_json = ld_page
    if article_json and save_debug:
        utils.write_file(article_json, './debug/article.json')

    oembed_json = None
    if 'skip_wp_oembed' not in args:
        el = soup.find('link', attrs={"type": "application/json+oembed"})
        if el:
            oembed_json = utils.get_url_json(el['href'])

    data_layer = None
    el = soup.find('script', string=re.compile(r'var tempDataLayer'))
    if el:
        m = re.search(r'var tempDataLayer = Object\((.*?)\);\n', el.string)
        if m:
            try:
                data_layer = json.loads(m.group(1))
            except:
                logger.warning('unable to load tempDataLayer in ' + url)

    if site_json.get('wpjson_path') and 'embed' not in args:
        args_copy = args.copy()
        args_copy['embed'] = True
        item = wp_posts.get_content(page_url, args_copy, site_json, save_debug, soup)
    else:
        item = {}

    if not item.get('id'):
        el = soup.find('link', attrs={"rel": "shortlink"})
        if el:
            # item['url'] = el['href']
            m = re.search(r'p=(\d+)', urlsplit(el['href']).query)
            if m:
                item['id'] = m.group(1)

        if not item.get('id'):
            el = soup.find(id=re.compile(r'post-\d+'))
            if el:
                m = re.search(r'post-(\d+)', el['id'])
                if m:
                    item['id'] = m.group(1)

        if not item.get('id'):
            m = re.search(r'"articleId","(\d+)"', page_html)
            if m:
                item['id'] = m.group(1)

        if not item.get('id') and article_json and article_json.get('@id'):
            item['id'] = article_json['@id']

    if meta and meta.get('og:url'):
        item['url'] = meta['og:url']
    elif article_json and article_json.get('url'):
        item['url'] = article_json['url']
    elif article_json and article_json.get('mainEntityOfPage'):
        if isinstance(article_json['mainEntityOfPage'], str):
            item['url'] = article_json['mainEntityOfPage']
        elif isinstance(article_json['mainEntityOfPage'], dict):
            item['url'] = article_json['mainEntityOfPage']['@id']
    else:
        el = soup.find('link', attrs={"rel": "canonical"})
        if el:
            item['url'] = el['href']
        else:
            item['url'] = page_url

    if not item.get('id') and item.get('url'):
        item['id'] = item['url']

    if not item.get('title'):
        if site_json.get('title'):
            el = utils.get_soup_elements(site_json['title'], soup)
            if el:
                item['title'] = el[0].get_text().strip()
        if not item.get('title'):
            if article_json and article_json.get('headline'):
                item['title'] = article_json['headline']
            elif meta and meta.get('og:title'):
                if isinstance(meta['og:title'], list):
                    item['title'] = meta['og:title'][0]
                else:
                    item['title'] = meta['og:title']
            elif meta and meta.get('twitter:title'):
                if isinstance(meta['twitter:title'], list):
                    item['title'] = meta['twitter:title'][0]
                else:
                    item['title'] = meta['twitter:title']
            elif oembed_json and oembed_json['title']:
                item['title'] = oembed_json['title']
            elif article_json and article_json.get('name'):
                item['title'] = article_json['name']
            elif parsley_page and parsley_page.get('title'):
                item['title'] = parsley_page['title']
            elif parsley_meta and parsley_meta.get('title'):
                item['title'] = parsley_meta['title']
        if not item.get('title') and soup.title:
            item['title'] = soup.title.get_text()
        item['title'] = item['title'].replace('&amp;', '&')
        if item.get('title') and re.search(r'#\d+|&\w+;', item['title']):
            item['title'] = html.unescape(item['title'])
        if site_json.get('site_title') and site_json['site_title'] in item['title']:
            item['title'] = re.sub(r'(.*?)\s+[–-]\s+{}'.format(site_json['site_title']), r'\1', item['title'], flags=re.I)

    if not item.get('date_published'):
        date = ''
        if data_layer and 'pageDetails' in data_layer and 'pubDate' in data_layer['pageDetails']:
            date = data_layer['pageDetails']['pubDate']
        elif meta and meta.get('article:published_time'):
            if isinstance(meta['article:published_time'], list):
                date = meta['article:published_time'][0]
            else:
                date = meta['article:published_time']
        elif meta and meta.get('published_at'):
            if isinstance(meta['published_at'], list):
                date = meta['published_at'][0]
            else:
                date = meta['published_at']
        elif article_json and article_json.get('datePublished'):
            date = article_json['datePublished']
        else:
            el = soup.find('time', attrs={"datetime": True})
            if el:
                date = el['datetime']
                if not re.search(r'[+\-]\d{2}:?\d{2}', date):
                    if site_json.get('timezone'):
                        dt_loc = datetime.fromisoformat(date)
                        tz_loc = pytz.timezone(site_json['timezone'])
                        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                        date = dt.isoformat()
                    else:
                        date += '+00:00'
        if date:
            try:
                if date.isnumeric():
                    dt = datetime.fromtimestamp(int(date))
                else:
                    dt = datetime.fromisoformat(date)
            except:
                dt = dateutil.parser.parse(date)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
        elif site_json.get('date'):
            for el in utils.get_soup_elements(site_json['date'], soup):
                try:
                    if el.name == 'meta':
                        date = el['content']
                    else:
                        date = el.get_text().strip()
                    if site_json['date'].get('date_regex'):
                        m = re.search(site_json['date']['date_regex'], date, flags=re.S)
                        if m:
                            date = m.group(site_json['date']['date_regex_group']).strip()
                    if site_json['date'].get('strptime'):
                        dt = datetime.strptime(date, site_json['date']['strptime'])
                    else:
                        dt = dateutil.parser.parse(date)
                    if not dt.tzname():
                        dt_loc = dt
                        if site_json['date'].get('tz'):
                            if site_json['date']['tz'] == 'local':
                                tz_loc = pytz.timezone(config.local_tz)
                            else:
                                tz_loc = pytz.timezone(site_json['date']['tz'])
                            dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
                        else:
                            dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    item['date_published'] = dt.isoformat()
                    item['_timestamp'] = dt.timestamp()
                    item['_display_date'] = utils.format_display_date(dt)
                except:
                    # This is for displaying content, the real date to be substituted from the rss feed
                    item['_display_date'] = date
                break
        else:
            # print(item['url'])
            m = re.search(r'/(2[01][123]\d)/([01]\d)/([0123]\d)/', item['url'])
            if m:
                dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                item['date_published'] = dt.isoformat()
                item['_timestamp'] = dt.timestamp()
                item['_display_date'] = utils.format_display_date(dt)

    if not item.get('date_modified'):
        date = ''
        if data_layer and 'pageDetails' in data_layer and 'updatedDate' in data_layer['pageDetails']:
            date = data_layer['pageDetails']['updatedDate']
        elif meta and meta.get('article:modified_time'):
            if isinstance(meta['article:modified_time'], list):
                date = meta['article:modified_time'][0]
            else:
                date = meta['article:modified_time']
        elif meta and meta.get('og:updated_time'):
            if isinstance(meta['og:updated_time'], list):
                date = meta['og:updated_time'][0]
            else:
                date = meta['og:updated_time']
        elif meta and meta.get('updated_at'):
            if isinstance(meta['updated_at'], list):
                date = meta['updated_at'][0]
            else:
                date = meta['updated_at']
        elif meta and meta.get('last-modified'):
            if isinstance(meta['last-modified'], list):
                date = meta['last-modified'][0]
            else:
                date = meta['last-modified']
        elif article_json and article_json.get('dateModified'):
            date = article_json['dateModified']
        if date:
            try:
                dt = datetime.fromisoformat(date).astimezone(timezone.utc)
            except:
                try:
                    dt = dateutil.parser.parse(date).astimezone(timezone.utc)
                except:
                    dt = None
            if dt:
                if 'date_published' not in item:
                    item['date_published'] = dt.isoformat()
                    item['_timestamp'] = dt.timestamp()
                    item['_display_date'] = utils.format_display_date(dt)
                else:
                    item['date_modified'] = dt.isoformat()

    if not item.get('author'):
        authors = []
        if site_json.get('author'):
            for el in utils.get_soup_elements(site_json['author'], soup):
                author = ''
                if el.name == 'meta':
                    author = el['content']
                elif el.name == 'a':
                    author = el.get_text().strip()
                else:
                    for it in el.find_all('a', href=re.compile(r'author|correspondents|staff')):
                        author = it.get_text().strip()
                        if author not in authors:
                            authors.append(author)
                if not authors and 'author_regex' in site_json['author']:
                    m = re.search(site_json['author']['author_regex'], el.get_text().strip())
                    if m:
                        authors.append(m.group(site_json['author']['author_regex_group']).strip())
                if not authors and el.get_text().strip():
                    author = re.sub(r'^By:?\s*(.*?)[\s\W]*$', r'\1', el.get_text().strip(), flags=re.I)
                if author:
                    author = re.sub(r'(.*?),\s?Associated Press$', r'\1 (Associated Press)', author)
                    author = author.replace(',', '&#44;')
                    if author not in authors:
                        authors.append(author)
                if authors and not site_json['author'].get('multi'):
                    break
        elif article_json and article_json.get('author'):
            if isinstance(article_json['author'], dict):
                if article_json['author'].get('name'):
                    authors.append(article_json['author']['name'].replace(',', '&#44;'))
            elif isinstance(article_json['author'], list):
                for it in article_json['author']:
                    if it.get('name'):
                        authors.append(it['name'].replace(',', '&#44;'))
        if not authors and ld_people:
            if ld_people:
                for it in ld_people:
                    if it.get('name'):
                        authors.append(it['name'].replace(',', '&#44;'))
        if not authors and meta:
            if meta.get('author'):
                authors.append(meta['author'].replace(',', '&#44;'))
            elif meta.get('citation_author'):
                authors.append(meta['citation_author'].replace(',', '&#44;'))
            elif meta.get('parsely-author'):
                authors.append(meta['parsely-author'].replace(',', '&#44;'))
        if not authors and oembed_json and oembed_json.get('author_name'):
                authors.append(oembed_json['author_name'].replace(',', '&#44;'))
        if not authors and site_json.get('authors'):
            authors.append(site_json['authors']['default'])
        if authors:
            authors = [re.sub(r'^by\s+', '', x, flags=re.I) for x in authors]
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)).replace('&#44;', ',')
        elif site_json.get('authors'):
            item['author'] = {"name": site_json['authors']['default']}
        else:
            item['author'] = {"name": split_url.netloc}

    if not item.get('tags'):
        item['tags'] = []
        if site_json.get('tags'):
            for el in utils.get_soup_elements(site_json['tags'], soup):
                if el.name == 'a' or ('no_link' in site_json['tags'] and site_json['tags']['no_link'] == True):
                    item['tags'].append(el.get_text().strip())
                else:
                    for it in el.find_all('a'):
                        item['tags'].append(it.get_text().strip())
        elif article_json and article_json.get('keywords'):
            if isinstance(article_json['keywords'], list):
                for it in article_json['keywords']:
                    if isinstance(it, str):
                        item['tags'].append(it)
                    elif isinstance(it, list):
                        item['tags'] += it.copy()
            elif isinstance(article_json['keywords'], str):
                # Split & remove whitespace: https://stackoverflow.com/questions/4071396/split-by-comma-and-strip-whitespace-in-python
                item['tags'] = list(map(str.strip, article_json['keywords'].split(',')))
        elif meta and meta.get('article:tag'):
            if isinstance(meta['article:tag'], list):
                item['tags'] = meta['article:tag'].copy()
            elif isinstance(meta['article:tag'], str):
                item['tags'] = list(map(str.strip, meta['article:tag'].split(',')))
        elif meta and meta.get('parsely-tags'):
            item['tags'] = list(map(str.strip, meta['parsely-tags'].split(',')))
        elif meta and meta.get('keywords'):
            item['tags'] = list(map(str.strip, meta['keywords'].split(',')))
        elif article_json and article_json.get('articleSection') and isinstance(article_json['articleSection'], list):
            item['tags'] = article_json['articleSection'].copy()
        elif parsley_page:
            if parsley_page.get('section'):
                item['tags'].append(parsley_page['section'])
            if parsley_page.get('tags'):
                item['tags'] += parsley_page['tags'].copy()
        if not item.get('tags'):
            del item['tags']
        else:
            # Remove duplicates (case-insensitive)
            item['tags'] = list(dict.fromkeys([it.casefold() for it in item['tags']]))

    image_caption = ''
    if not item.get('_image'):
        if ld_images:
            item['_image'] = ld_images[0]['url']
            if ld_images[0].get('caption'):
                image_caption = ld_images[0]['caption']
        if not item.get('_image') and article_json:
            if article_json.get('image'):
                if isinstance(article_json['image'], dict):
                    if article_json['image'].get('url'):
                        item['_image'] = article_json['image']['url']
                        if article_json['image'].get('caption'):
                            image_caption = article_json['image']['caption']
                elif isinstance(article_json['image'], list):
                    if isinstance(article_json['image'][0], dict):
                        item['_image'] = article_json['image'][0]['url']
                        if article_json['image'][0].get('caption'):
                            image_caption = article_json['image'][0]['caption']
                    elif isinstance(article_json['image'][0], str):
                        item['_image'] = article_json['image'][0]
                elif isinstance(article_json['image'], str):
                    item['_image'] = article_json['image']
            if not item.get('_image') and article_json.get('thumbnailUrl'):
                item['_image'] = article_json['thumbnailUrl']
        if not item.get('_image') and meta and meta.get('og:image'):
            if isinstance(meta['og:image'], str):
                item['_image'] = meta['og:image']
            else:
                item['_image'] = meta['og:image'][0]
        elif oembed_json and oembed_json.get('thumbnail_url'):
            item['_image'] = oembed_json['thumbnail_url']

    if article_json and article_json.get('description'):
        item['summary'] = article_json['description']
    elif oembed_json and oembed_json.get('description'):
        item['summary'] = oembed_json['description']
    elif meta and meta.get('description'):
        item['summary'] = meta['description']
    elif meta and meta.get('og:description'):
        item['summary'] = meta['og:description']
    elif meta and meta.get('twitter:description'):
        item['summary'] = meta['twitter:description']
    elif 'summary' in site_json:
        for el in utils.get_soup_elements(site_json['summary'], soup):
            item['summary'] = el.get_text()

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    gallery = ''
    item['content_html'] = ''
    if site_json.get('subtitle'):
        subtitles = []
        for el in utils.get_soup_elements(site_json['subtitle'], soup):
            # print(el.get_text())
            subtitles.append(el.get_text())
        if subtitles:
            item['content_html'] += '<p><em>' + '<br/>'.join(subtitles) + '</em></p>'
    elif parsley_meta and parsley_meta.get('lower_deck'):
        item['content_html'] += '<p><em>' + parsley_meta['lower_deck'] + '</em></p>'
    elif 'add_subtitle' in args and item.get('summary'):
        item['content_html'] += '<p><em>' + item['summary'] + '</em></p>'

    if 'no_lede_caption' in args:
        add_caption = False
        caption = ''
    else:
        add_caption = True
        caption = ''
        if site_json.get('lede_caption'):
            elements = utils.get_soup_elements(site_json['lede_caption'], soup)
            if elements:
                captions = []
                for it in elements[0].find_all(class_=['content-image-caption', 'content-image-attribution']):
                    captions.append(it.decode_contents())
                if captions:
                    caption = ' | '.join(captions)
                else:
                    caption = elements[0].decode_contents()

    lede = False
    if site_json.get('lede_video'):
        elements = utils.get_soup_elements(site_json['lede_video'], soup)
        print(elements)
        if elements:
            # print(elements)
            el = elements[0]
            if el:
                if el.get('class') and 'hearstLumierePlayer' in el['class']:
                    video_json = utils.get_url_json('https://nitehawk.hearst.io/embeds/' + el['data-player-id'])
                    if video_json:
                        source = next((it for it in video_json['media']['transcodings'] if it['preset_name'] == 'apple_m3u8'), None)
                        if source:
                            item['content_html'] += utils.add_video(source['full_url'], 'application/x-mpegURL', video_json['media']['cropped_preview_image'], video_json['media']['title'])
                            lede = True
                        else:
                            source = next((it for it in video_json['media']['display_name'] if it['preset_name'] == '480p'), None)
                            if source:
                                item['content_html'] += utils.add_video(source['full_url'], 'video/mp4', video_json['media']['cropped_preview_image'], video_json['media']['title'])
                                lede = True
                            else:
                                item['content_html'] += utils.add_video(source[0]['full_url'], 'video/mp4', video_json['media']['cropped_preview_image'], video_json['media']['title'])
                                lede = True
                elif el.find(class_='jw-video-box'):
                    it = el.find(class_='jw-video-box')
                    item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/{}'.format(it['data-video']))
                    lede = True
                elif el.find(id=re.compile(r'jw-player-')):
                    it = el.find(id=re.compile(r'jw-player-'))
                    if article_json.get('video') and article_json['video'].get('embedUrl'):
                        item['content_html'] += utils.add_embed(article_json['video']['embedUrl'])
                        lede = True
                    elif article_json.get('video') and article_json['video'].get('contentUrl'):
                        item['content_html'] += utils.add_embed(article_json['video']['contentUrl'])
                        lede = True
                    else:
                        it = soup.find('script', string=re.compile(r'jwplayer\("{}"\)\.setup\('.format(it['id'])))
                        if it:
                            m = re.search(r'"mediaid":"([^"]+)"', it.string)
                            if m:
                                item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/{}'.format(m.group(1)))
                                lede = True
                elif el.find(class_='mntl-jwplayer'):
                    it = el.find(class_='mntl-jwplayer')
                    if it.get('data-bgset'):
                        m = re.search(r'/media/([^/]+)/', it['data-bgset'])
                        if m:
                            item['content_html'] += utils.add_embed('https://cdn.jwplayer.com/v2/media/{}'.format(m.group(1)))
                            lede = True
                elif el.find(class_='video-wrapper'):
                    it = el.find(class_='video-wrapper')
                    if it.get('data-type') and it['data-type'] == 'youtube':
                        item['content_html'] += utils.add_embed(it['data-src'])
                        lede = True
                elif el.find(class_='js-superdiv'):
                    it = el.find(class_='js-superdiv')
                    if it.get('data-video'):
                        video_json = json.loads(it['data-video'])
                        if it.img:
                            poster = it.img['src']
                        else:
                            poster = ''
                        item['content_html'] += utils.add_video(video_json['url'], 'video/mp4', poster, video_json['title'], use_videojs=True)
                        lede = True
                elif el.find('iframe'):
                    it = el.find('iframe')
                    item['content_html'] += utils.add_embed(it['src'])
                    lede = True
                elif el.name == 'iframe':
                    item['content_html'] += utils.add_embed(el['src'])
                    lede = True
                else:
                    logger.warning('unhandled lede video wrapper in ' + item['url'])

    if not lede and 'add_lede_video' in args and 'video' in article_json:
        if isinstance(article_json['video'], list):
            video = article_json['video'][0]
        elif isinstance(article_json['video'], dict):
            video = article_json['video']
        else:
            video = None
        if video:
            if '@type' in video and video['@type'] == 'VideoObject':
                if 'jwplayer' in video['contentUrl']:
                    item['content_html'] += utils.add_embed(video['contentUrl'])
                else:
                    poster = ''
                    if video.get('thumbnailUrl'):
                        if isinstance(video['thumbnailUrl'], str):
                            poster = video['thumbnailUrl']
                        elif isinstance(video['thumbnailUrl'], list):
                            poster = video['thumbnailUrl'][-1]
                    item['content_html'] += utils.add_video(video['contentUrl'], 'video/mp4', poster, video.get('name'), use_videojs=True)
            elif video.get('embedUrl'):
                item['content_html'] += utils.add_embed(video['embedUrl'])
                lede = True
            elif video.get('contentUrl'):
                item['content_html'] += utils.add_embed(video['contentUrl'])
                lede = True

    if not lede and site_json.get('lede_img'):
        elements = utils.get_soup_elements(site_json['lede_img'], soup)
        if elements:
            # print(elements)
            el = elements[0]
            if el:
                if el.find(class_='rslides'):
                    it = el.find('li')
                    item['content_html'] += wp_posts.add_image(copy.copy(it), None, base_url, site_json, caption, add_caption)
                    lede = True
                    gallery = '<h3>Gallery</h3>' + wp_posts.format_content(str(el), item, site_json, module_format_content, soup)
                elif el.get('class') and 'st-image-gallery' in el['class']:
                    gallery_json = json.loads(el['data-gallery'])
                    gallery_url = ''
                    if len(gallery_json['images']) > 1:
                        gallery_images = []
                        new_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                        for image in gallery_json['images']:
                            img_src = utils.image_from_srcset(image['srcset'], 2000)
                            thumb = utils.image_from_srcset(image['srcset'], 800)
                            if image.get('caption'):
                                caption = image['caption']
                            else:
                                caption = ''
                            new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, caption, link=img_src) + '</div>'
                            gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
                        new_html += '</div>'
                        gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                        gallery = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + new_html
                    image = gallery_json['images'][0]
                    img_src = utils.image_from_srcset(image['srcset'], 1200)
                    if image.get('caption'):
                        caption = image['caption']
                    else:
                        caption = ''
                    if gallery_url:
                        if caption:
                            caption += '<br>'
                        caption += '<a href="{}">View photo gallery</a>'.format(gallery_url)
                    item['content_html'] += utils.add_image(img_src, caption)
                    lede = True
                elif el.find('img') or (el.get('style') and 'background-image' in el['style']):
                    item['content_html'] += wp_posts.add_image(el, el, base_url, site_json, caption, add_caption)
                    lede = True
                elif el.get('data-bg'):
                    img_src = el['data-bg']
                    if img_src.startswith('/'):
                        img_src = base_url + img_src
                    item['content_html'] += utils.add_image(img_src)
                    lede = True
                elif el.find('iframe'):
                    item['content_html'] += utils.add_embed(el.find('iframe')['src'])
                    lede = True
                else:
                    logger.warning('unhandled lede_img in ' + item['url'])
    if 'add_lede_img' in args and not lede and item.get('_image'):
        item['content_html'] += utils.add_image(wp_posts.resize_image(item['_image'], site_json), image_caption)

    if site_json.get('add_content'):
        for it in site_json['add_content']:
            if not it.get('position') or it['position'] == 'top':
                contents = utils.get_soup_elements(it, soup)
                for el in contents:
                    # print(el)
                    if 'title' in it:
                        item['content_html'] += it['title']
                    if 'unwrap' in it and it['unwrap'] == False:
                        item['content_html'] += wp_posts.format_content(str(el), item, site_json, module_format_content, soup)
                    else:
                        item['content_html'] += wp_posts.format_content(el.decode_contents(), item, site_json, module_format_content, soup)
                if it.get('separator'):
                    item['content_html'] += '<div>&nbsp;</div><hr style="width:80%; margin:auto;"/><div>&nbsp;</div>'

    if site_json.get('content'):
        if isinstance(site_json['content'], list):
            for content in site_json['content']:
                contents = utils.get_soup_elements(content, soup)
                for el in contents:
                    item['content_html'] += wp_posts.format_content(el.decode_contents(), item, site_json, module_format_content, soup)
        else:
            contents = utils.get_soup_elements(site_json['content'], soup)
            for el in contents:
                item['content_html'] += wp_posts.format_content(el.decode_contents(), item, site_json, module_format_content, soup)

    if site_json.get('add_content'):
        for it in site_json['add_content']:
            if it['position'] != 'top':
                contents = utils.get_soup_elements(it, soup)
                if contents and it.get('separator'):
                    item['content_html'] += '<div>&nbsp;</div><hr style="width:80%; margin:auto;"/><div>&nbsp;</div>'
                if 'title' in it:
                        item['content_html'] += it['title']
                for el in contents:
                    if 'unwrap' in it and it['unwrap'] == False:
                        item['content_html'] += wp_posts.format_content(str(el), item, site_json, module_format_content, soup)
                    else:
                        item['content_html'] += wp_posts.format_content(el.decode_contents(), item, site_json, module_format_content, soup)

    if gallery:
        item['content_html'] += gallery

    if site_json.get('text_encode'):
        def encode_item(item, enc):
            if isinstance(item, str):
                # print(item)
                item = item.encode(enc, 'replace').decode('utf-8', 'replace')
            elif isinstance(item, list):
                for i, it in enumerate(item):
                    item[i] = encode_item(it, enc)
            elif isinstance(item, dict):
                for key, val in item.items():
                    item[key] = encode_item(val, enc)
            return item
        encode_item(item, site_json['text_encode'])

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
