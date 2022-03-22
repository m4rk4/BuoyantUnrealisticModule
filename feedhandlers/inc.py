import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import unquote_plus, urlsplit

import utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def add_video(article_id, video_id):
    api_url = 'https://api.inc.com/rest/videorequest/{}'.format(article_id)
    video_json = utils.get_url_json(api_url)
    if not video_json:
        return ''
    video = next((it for it in video_json['videos'] if it['id'] == int(video_id)), None)
    if not video:
        logger.warning('video {} not found in {}'.format(video_id, api_url))
        return ''
    jw_json = utils.get_url_json('https://content.jwplatform.com/feeds/{}.json'.format(video['vid_jw_identifier']))
    if not jw_json:
        return ''
    video_sources = []
    for vid_src in jw_json['playlist'][0]['sources']:
        if vid_src['type'] == 'video/mp4':
            video_sources.append(vid_src)
    vid_src = utils.closest_dict(video_sources, 'height', 480)
    poster = utils.closest_dict(jw_json['playlist'][0]['images'], 'width', 1080)
    return utils.add_video(vid_src['file'], 'video/mp4', poster['src'])


def add_inline_image(image_id):
    api_json = utils.get_url_json('https://api.inc.com/rest/inlineimage/{}'.format(image_id))
    if not api_json:
        return ''
    image_json = api_json['data']
    imageref = re.sub(r'\.(.*)$', r'_{}.\1'.format(image_json['id']), image_json['inl_imageref'])
    img_src = 'https://www.incimages.com/uploaded_files/inlineimage/630x0/{}'.format(imageref)
    captions = []
    if image_json.get('inl_caption'):
        captions.append(image_json['inl_caption'])
    if image_json.get('inl_custom_credit'):
        captions.append(image_json['inl_custom_credit'])
    return utils.add_image(img_src, ' | '.join(captions))


def add_image(image_json, width=1000):
    img_src = get_img_src(image_json, width)
    captions = []
    if image_json.get('inl_caption'):
        captions.append(image_json['inl_caption'])
    if image_json.get('inl_caption'):
        captions.append(image_json['inl_customcredit'])
    return utils.add_image(img_src, ' | '.join(captions))


def get_img_src(image_json, width=1000):
    # Only for panoramic images
    img_src = image_json['sizes']['panoramic']['original']
    if img_src.startswith('https'):
        return img_src.replace('/upload/', '/upload/w_{},c_fill/'.format(width))
    images = []
    for key, val in image_json['sizes']['panoramic'].items():
        m = re.search('(\d+)x(\d+)', key)
        if m:
            image = {}
            image['width'] = int(m.group(1))
            image['height'] = int(m.group(2))
            image['src'] = val
            images.append(image)
    image = utils.closest_dict(images, 'width', width)
    return 'https://www.incimages.com/' + image['src']


def get_datetime(date):
    tz_est = pytz.timezone('US/Eastern')
    dt_est = datetime.fromisoformat(date)
    return tz_est.localize(dt_est).astimezone(pytz.utc)

def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    api_url = 'https://api.inc.com/rest/byfilelocation' + split_url.path
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    article_json = api_json['article']
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['id']
    item['url'] = url
    item['title'] = article_json['inc_headline']

    # dates seem to be EST
    dt = get_datetime(article_json['inc_pubdate'])
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = get_datetime(article_json['time_updated'])
    item['date_modified'] = dt.isoformat()

    authors = []
    for author in article_json['authors']:
        authors.append(author['aut_name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    if article_json.get('channels'):
        item['tags'] = []
        for it in article_json['channels']:
            item['tags'].append(it['cnl_name'])

    if article_json.get('images'):
        item['_image'] = get_img_src(article_json['imagemodels'][0])

    item['summary'] = article_json['meta_description']

    item['content_html'] = ''
    if article_json.get('inc_deck'):
        item['content_html'] += '<p><em>{}</em></p>'.format(article_json['inc_deck'])

    if '/video/' in url:
        item['content_html'] += add_video(item['id'], article_json['videos'][0]['id'])
        return item

    if not article_json.get('formatted_text'):
        logger.warning('article text not available for ' + url)
        return item

    soup = BeautifulSoup(article_json['formatted_text'], 'html.parser')

    for el in soup.find_all(class_='inlineimage'):
        new_html = add_inline_image(el['data-content-id'])
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all(class_='inlinevideo'):
        new_html = add_video(item['id'], el['data-content-id'])
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all(class_='youtube-embed-wrapper'):
        if el.iframe and el.iframe.get('src'):
            new_html = utils.add_embed(el.iframe['src'])
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled youtube-embed-wrapper in ' + url)

    for el in soup.find_all(class_='twitter-tweet'):
        tweet_url = ''
        if el.name == 'div':
            if el.iframe and el.iframe.get('data-tweet-id'):
                tweet_url = utils.get_twitter_url(el.iframe['data-tweet-id'])
            elif el.iframe and el.iframe.get('src'):
                m = re.search(r'\bid=(\d+)\b', unquote_plus(el.iframe['src']))
                if m:
                    tweet_url = utils.get_twitter_url(m.group(1))
        elif el.name == 'blockquote':
            tweet_url = el.find_all('a')[-1]['href']
        if tweet_url:
            new_html = utils.add_embed(tweet_url)
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled twitter-tweet in ' + url)

    for el in soup.find_all(class_='pullquote'):
        new_html = utils.add_pullquote(el.get_text())
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all('blockquote'):
        new_html = utils.add_blockquote(el.get_text())
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all(class_='mag_sidebar'):
        new_html = ''
        for group in el.find_all(class_='group'):
            if new_html:
                new_html += '<br/><br/>'
            it = group.find(class_='grouptitle')
            new_html += '<strong style="font-size:1.2em;">{}</strong>'.format(it.get_text())
            for it in group.find_all(class_='grouptext'):
                new_html += '<br/><small>{}</small>'.format(it.get_text())
        el.insert_after(BeautifulSoup(utils.add_blockquote(new_html), 'html.parser'))
        el.decompose()

    for el in soup.find_all('script'):
        el.decompose()

    for el in soup.find_all(class_=True):
        logger.warning('unhandled element {} with class {} in {}'.format(el.name, el['class'], url))

    if article_json.get('images'):
        item['content_html'] += add_image(article_json['imagemodels'][0])

    item['content_html'] += str(soup)
    return item


def get_feed(args, save_debug=False):
    # https://www.inc.com/rest/category/startup
    # https://www.inc.com/rest/homepackages
    # https://www.inc.com/rest/magazinetoc
    # https://www.inc.com/rss/
    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    if paths[0] == 'rss':
        return rss.get_feed(args, save_debug, get_content)
    elif paths[0] == 'category':
        api_url = 'https://api.inc.com/rest' + split_url.path
    elif paths[0] == 'author':
        api_url = 'https://api.inc.com/rest' + split_url.path
    elif paths[0] == 'channel':
        api_url = 'https://api.inc.com/rest/channeltop/' + paths[1]
    elif len(paths) == 1:
        api_url = 'https://api.inc.com/rest/channeltop/' + paths[0]
    else:
        logger.warning('unhandled rss url ' + args['url'])
        return None

    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/feed.json')

    articles = []
    if api_json['data'].get('channelObj'):
        for key in ['mainfeatures', 'morearticles']:
            for item in api_json['data'][key]:
                article = item.copy()
                dt = get_datetime(item['pubdate'])
                article['_timestamp'] = dt.timestamp()
                # Check age
                if 'age' in args:
                    if not utils.check_age(article, args):
                        continue
                articles.append(article)
    elif paths[0] == 'catetory':
        pass
    elif paths[0] == 'author':
        articles = api_json['data']['articlelist'].copy()

    n = 0
    items = []
    for article in articles:
        url = article['baseurl'] + article['inc_filelocation']
        if save_debug:
            logger.debug('getting contents for ' + url)
        item = get_content(url, args, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break

    feed = utils.init_jsonfeed(args)
    feed['home_page_url'] = args['url']
    if paths[0] == 'rss':
        pass
    elif paths[0] == 'author' or paths[0] == 'channel' or paths[0] == 'category':
        feed['title'] = '{} > {}'.format(split_url.netloc, paths[1])
    else:
        feed['title'] = '{} > {}'.format(split_url.netloc, paths[0])
    feed['items'] = sorted(items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
