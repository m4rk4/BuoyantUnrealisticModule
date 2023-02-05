import html, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    if not 'fivethirtyeight.com' in img_src:
        return img_src
    split_url = urlsplit(img_src)
    return '{}://{}{}?w={}'.format(split_url.scheme, split_url.netloc, split_url.path, width)


def add_media(media_json, media_url=''):
    if not media_json and media_url:
        media_json = utils.get_url_json(media_url)
    if not media_json:
        return ''
    if media_json['media_type'] == 'image':
        img_src = resize_image(media_json['source_url'])
        caption = media_json['media_details']['image_meta']['caption']
        return utils.add_image(img_src, caption)
    else:
        logger.warning('unhandled media type {} in {}'.format(media_json['media_type'], media_json['_links']['self'][0]['href']))
    return ''


def add_image(figure):
    if figure.img and figure.img.get('src'):
        img_src = figure.img['src']
    else:
        logger.warning('unable to find image src in ' + str(figure))
        return ''

    if figure.figcaption:
        el = figure.figcaption.find(class_='credit')
        if el:
            credit = el.get_text()
            el.decompose()
        else:
            credit = ''
        caption = figure.figcaption.get_text().strip()
        if caption and credit:
            caption += ' | ' + credit
        elif credit:
            caption = credit
    else:
        caption = ''

    return utils.add_image(resize_image(img_src), caption)


def get_liveblog_content(liveblog_id, save_debug):
    tz_est = pytz.timezone('US/Eastern')
    est_now = pytz.utc.localize(datetime.utcnow()).astimezone(tz_est)
    ts = int(est_now.timestamp())
    entries_url = 'https://fivethirtyeight.com/wp-json/liveblog/v1/{}/get-entries/1/{}'.format(liveblog_id, ts)
    entries_json = utils.get_url_json(entries_url)
    if not entries_json:
        return None
    if save_debug:
        utils.write_file(entries_json, './debug/blog.json')

    content_html = ''
    for entry in entries_json['entries']:
        dt = datetime.fromtimestamp(entry['timestamp'])
        date = utils.format_display_date(dt)
        content_html += '<div style="margin:0.5em; padding:0.5em; background-color:#ccc;"><small>{}</small><br><strong>{}</strong>{}</div>'.format(date, entry['authors'][0]['name'], entry['render'])
    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))
    wp_url = ''
    if paths[0] == 'features':
        wp_url = 'https://fivethirtyeight.com/wp-json/wp/v2/fte_features?slug=' + paths[1]
    elif paths[0] == 'videos':
        wp_url = 'https://fivethirtyeight.com/wp-json/wp/v2/fte_videos?slug=' + paths[1]
    elif paths[0] == 'live-blog':
        wp_url = 'https://fivethirtyeight.com/wp-json/wp/v2/fte_liveblog?slug=' + paths[1]
    elif 'projects' in split_url.netloc:
        post_html = utils.get_url_html(url)
        if post_html:
            m = re.search(r'postId:\s"(\d+)"', post_html)
            if m:
                wp_url = 'https://fivethirtyeight.com/wp-json/wp/v2/fte_interactives/' + m.group(1)

    if not wp_url:
        logger.warning('unhandled url ' + url)
        return None

    wp_json = utils.get_url_json(wp_url)
    if not wp_json:
        return None

    if isinstance(wp_json, list):
        post_json = wp_json[0]
    else:
        post_json = wp_json
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    soup = BeautifulSoup(post_json['content']['rendered'], 'html.parser')

    item = {}
    item['id'] = post_json['id']
    item['url'] = post_json['link']
    item['title'] = html.unescape(post_json['title']['rendered'])

    dt = datetime.fromisoformat(post_json['date_gmt'] + '+00:00')
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post_json['modified_gmt'] + '+00:00')
    item['date_modified'] = dt.isoformat()

    # The author endpoint doesn't work
    # e.g. https://fivethirtyeight.com/wp-json/wp/v2/users/30
    item['author'] = {}
    authors = []
    for el in soup.find_all(class_='author'):
        authors.append(el.get_text())
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        page_details = utils.get_url_json('https://fivethirtyeight.com/wp-json/dtci_datalayer/v1/get_page_details/{}'.format(post_json['id']))
        if page_details and page_details.get('author'):
            item['author']['name'] = page_details['author']
        else:
            item['author']['name'] = 'FiveThirtyEight'

    if post_json['_links'].get('wp:term'):
        item['tags'] = []
        for wp_term in post_json['_links']['wp:term']:
            term_json = utils.get_url_json(wp_term['href'])
            if term_json:
                for term in term_json:
                    item['tags'].append(term['name'])
        if not item.get('tags'):
            del item['tags']

    media_json = None
    if post_json['_links'].get('wp:featuredmedia'):
        media_json = utils.get_url_json(post_json['_links']['wp:featuredmedia'][0]['href'])
        if media_json:
            item['_image'] = media_json['source_url']

    item['content_html'] = ''
    if post_json['type'] == 'fte_interactives':
        item['content_html'] += '<h2>Interactive articles are best view on the <a href="{}">website</a></h2>'.format(item['url'])
    elif post_json['type'] == 'fte_videos':
        # where to find the video id without parsing the html page?
        # https://abcnews.go.com/video/itemfeed?id=83446947&requestor=fivethirtyeight
        video_html = utils.get_url_html(url)
        if video_html:
            video_soup = BeautifulSoup(video_html, 'html.parser')
            for el in video_soup.find_all('script', attrs={"type":"application/ld+json"}):
                ld_json = json.loads(el.string)
                if ld_json['@type'] == 'NewsArticle':
                    item['_video'] = ld_json['video']['contentUrl']
                    item['content_html'] += utils.add_video(ld_json['video']['contentUrl'], 'video/mp4', ld_json['video']['thumbnailUrl'], ld_json['video']['name'])
                    break

    if post_json['type'] == 'fte_liveblog':
        liveblog = get_liveblog_content(post_json['id'], save_debug)
        soup = BeautifulSoup(liveblog, 'html.parser')

    if not item.get('_video'):
        el = soup.find(class_=re.compile(r'article-header'))
        if el:
            figure = el.find('figure', class_='single-featured-image')
            if figure:
                item['content_html'] += add_image(figure)
            el.decompose()
        elif media_json:
            item['content_html'] += add_media(media_json)

    el = soup.find(class_='abc__series')
    if el:
        it = el.find(class_='abc__series-text')
        if it:
            el.insert_after(it.p)
            el.decompose()

    for el in soup.find_all(class_='wp-block-image'):
        new_html = ''
        figure = None
        if el.name == 'figure':
            figure = el
        elif el.figure:
            figure = el.figure
        if figure:
            new_html = add_image(figure)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled wp-block-image in ' + url)

    for el in soup.find_all('img', class_=re.compile(r'wp-image-\d+')):
        if post_json['type'] == 'fte_liveblog':
            new_html = utils.add_image(el['src'], fig_style='width:80%; margin-left:auto; margin-right:auto; padding:0;')
        else:
            new_html = utils.add_image(resize_image(el['src']))
        if el.parent and el.parent.name == 'p':
            el.parent.insert_before(BeautifulSoup(new_html, 'html.parser'))
            if not el.parent.get_text().strip():
                el.parent.unwrap()
        else:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all(class_='wp-block-embed'):
        embed_src = ''
        if el.iframe and el.iframe.get('src'):
            embed_src = el.iframe['src']
        elif el.blockquote:
            if 'twitter-tweet' in el.blockquote['class']:
                embed_src = el.find_all('a')[-1]['href']
        if embed_src:
            new_html = utils.add_embed(embed_src)
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled wp-block-embed in ' + url)

    for el in soup.find_all(class_='non-jetpack-embed'):
        embed_src = ''
        if el.iframe and el.iframe.get('src'):
            embed_src = el.iframe['src']
        elif el.blockquote:
            if 'twitter-tweet' in el.blockquote['class']:
                embed_src = el.find_all('a')[-1]['href']
        if embed_src:
            new_html = utils.add_embed(embed_src)
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled non-jetpack-embed in ' + url)

    for el in soup.find_all('iframe'):
        new_html = ''
        if el.get('src'):
            src = ''
            if el['src'].startswith('https://fivethirtyeight.com/player/'):
                m = re.search('src=([^&]+)', el['src'])
                if m:
                    src = unquote_plus(m.group(1))
            if not src:
                src = el['src']
            src = utils.get_redirect_url(src)
            new_html = utils.add_embed(src)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled iframe in ' + url)

    for el in soup.find_all(class_='core-html'):
        it = soup.new_tag('hr')
        el.insert_before(it)
        it = soup.new_tag('hr')
        el.insert_after(it)
        el.unwrap()

    for el in soup.find_all('section', class_='viz'):
        if el.header:
            it = el.header.find(class_='title')
            if it:
                it.name = 'h3'
                it['style'] = 'margin-bottom:0;'
            it = el.header.find(class_='subtitle')
            if it:
                it['style'] = 'margin-top:0;'
        if el.footer:
            el.footer['style'] = 'font-size:0.8em;'
            for it in el.footer.find_all('p'):
                it['style'] = 'margin-top:0.5em; margin-bottom:0;'
                if it.get('class') and 'source' in it['class']:
                    it['style'] += ' text-transform:uppercase;'
        if el.table:
            el.table['style'] = 'width:90%; margin-left:auto; margin-right:auto;'

    for el in soup.find_all('header', class_='post-info'):
        el.decompose()

    item['content_html'] += str(soup)
    return item

def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
