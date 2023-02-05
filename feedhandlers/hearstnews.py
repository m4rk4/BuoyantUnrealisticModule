import json, re, pytz, tldextract
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wp_posts

import logging

logger = logging.getLogger(__name__)


def add_image(image, width=1000):
    img_src = image['sizes']['original']['url'].replace('rawImage', '{}x0'.format(width))
    captions = []
    if image.get('caption'):
        captions.append(image['caption']['plain'])
    if image.get('byline'):
        captions.append(image['byline'])
    return utils.add_image(img_src, ' | '.join(captions))


def add_hst_exco_video(player_id):
    player_url = 'https://player.ex.co/player/' + player_id
    player = utils.get_url_html(player_url)
    if not player:
        return None
    m = re.search(r'window\.STREAM_CONFIGS\[\'{}\'\] = (.*?);\n'.format(player_id), player)
    if not m:
        logger.warning('unable to find STREAM_CONFIGS in ' + player_url)
        return None
    stream_config = json.loads(m.group(1))
    utils.write_file(stream_config, './debug/video.json')
    return utils.add_video(stream_config['contents'][0]['video']['mp4']['src'], 'video/mp4', stream_config['contents'][0]['poster'], stream_config['contents'][0]['title'])


def render_content(content):
    content_html = ''
    if content['type'] == 'text':
        content_html += content['params']['html1']

    elif content['type'] == 'image':
        content_html += add_image(content['params'])

    elif content['type'] == 'gallery':
        content_html += '<h3>Gallery</h3>'
        for slide in content['params']['slides']:
            content_html += render_content(slide)

    elif content['type'] == 'video' and content['params']['originalSource'] == 'jwplayer':
        content_html += utils.add_embed(content['params']['playerUrl'])

    elif content['type'] == 'embed':
        if content['params'].get('embedType'):
            if content['params']['embedType'] == 'youtube' or content['params']['embedType'] == 'facebook':
                content_html += utils.add_embed(content['params']['attributes']['iframe_data-url'])
            elif content['params']['embedType'] == 'twitter':
                content_html += utils.add_embed(content['params']['attributes']['a_href'])
            elif content['params']['embedType'] == 'instagram':
                content_html += utils.add_embed(content['params']['attributes']['blockquote_data-instgrm-permalink'])
            elif content['params']['embedType'] == 'commerceconnector':
                soup = BeautifulSoup(content['params']['html2'], 'html.parser')
                img = soup.find('img')
                split_url = urlsplit(content['params']['attributes']['a_href'])
                content_html += '<table><tr><td style="width:200px;"><a href="{}"><img style="width:200px;" src="{}"/></a></td><td style="vertical-align:top;"><a href="{}"><b>{}</b></a><br/>{} | {}</td></tr></table>'.format(content['params']['attributes']['a_href'], content['params']['attributes']['img_src'], content['params']['attributes']['a_href'], img['title'], content['params']['attributes']['a_data-vars-ga-product-custom-brand'], split_url.netloc)
            else:
                logger.warning('unsupported embedType ' + content['params']['embedType'])
        elif content['params'].get('attributes') and content['params']['attributes'].get('div_class') and content['params']['attributes']['div_class'] == 'hst-exco-player':
            pass
        elif content['params'].get('attributes') and content['params']['attributes'].get('script_id') and content['params']['attributes']['script_id'] == 'hst-exco-player-code':
            pass
            # m = re.search(r'playerId = \'([^\']+)\'', content['params']['html1'])
            # if m:
            #     content_html += add_hst_exco_video(m.group(1))
            # else:
            #     logger.warning('unknown hst-exco-player-code playerId')
        elif re.search(r'<iframe', content['params']['html1']):
            m = re.search(r'src="([^"]+)"', content['params']['html1'])
            if m:
                iframe_src = m.group(1)
                if content['params']['attributes'].get('div_class') and content['params']['attributes']['div_class'] == 'hnp-iframe-wrapper':
                    m = re.search(r'iframe-([^-]+)-wrapper', content['params']['attributes']['div_id'])
                    if m:
                        content_html += utils.add_embed('https://cdn.jwplayer.com/players/{}-.js'.format(m.group(1)))
                    else:
                        content_html += utils.add_embed(iframe_src)
                else:
                    content_html += utils.add_embed(iframe_src)
            else:
                logger.warning('unhandled iframe embed')
        else:
            logger.warning('unhandled embed')

    elif content['type'] == 'card':
        content_html += '<h3>{}</h3>'.format(content['params']['title'])
        for it in content['params']['body']:
            content_html += render_content(it)

    elif content['type'] == 'interstitial' and content['params'].get('subtype1') and content['params']['subtype1'] == 'taboola':
        pass

    elif content['type'] == 'ad':
        pass

    else:
        logger.warning('unhandled content type ' + content['type'])

    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if split_url.netloc.startswith('storystudio'):
        return wp_posts.get_content(url, args, site_json, save_debug)
    m = re.search(r'-(\d+)\.php', split_url.path)
    if not m:
        logger.warning('unable to determine content id from ' + url)
        return None
    content_id = m.group(1)
    api_url = '{}://{}/api/v1/'.format(split_url.scheme, split_url.netloc)
    if '/slideshow/' in split_url.path:
        api_url += 'slideshow/'
    else:
        api_url += 'article/'
    api_url += '?id={}&content=full&imageSizes=original'.format(content_id)
    #print(api_url)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    content_json = api_json['result'][content_id]

    if content_json.get('isPaidadContent'):
        logger.debug('article is Paid Advertising. skipping ' + url)
        return None

    item = {}
    item['id'] = content_id
    item['url'] = content_json['url']
    item['title'] = content_json['title']

    tz = pytz.timezone(api_json['meta']['publishingSiteTimezone'])
    dt_loc = datetime.fromtimestamp(content_json['publicationDateTimestamp'])
    dt_utc = tz.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt_utc.isoformat()
    item['_timestamp'] = dt_utc.timestamp()
    item['_display_date'] = utils.format_display_date(dt_utc)

    dt_loc = datetime.fromtimestamp(content_json['lastModifiedDateTimestamp'])
    dt_utc = tz.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt_utc.isoformat()

    authors = []
    for it in content_json['authors']:
        if it.get('name'):
            authors.append(it['name'])
    if authors:
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    elif 'AP' in content_json['keyNlpOrganization']:
        item['author'] = {"name": "AP News"}

    item['tags'] = []
    for key, val in content_json.items():
        if key.startswith('key') and val:
            item['tags'] += val
    if not item.get('tags'):
        del item['tags']

    if content_json.get('image'):
        item['_image'] = content_json['image']['original']['url'].replace('rawImage', '1000x0')

    item['summary'] = content_json['abstract']

    item['content_html'] = ''
    if content_json['body'][0]['type'] == 'gallery':
        item['content_html'] += add_image(content_json['body'][0]['params']['cover'])
    elif content_json['body'][0]['type'] != 'image' and item.get('_image'):
        item['content_html'] += utils.add_image(item['_image'])

    if content_json['type'] == 'slideshow':
        for content in content_json['body']:
            if content['type'] == 'gallery':
                for slide in content['params']['slides']:
                    item['content_html'] += '<h2>{}</h2>'.format(slide['params']['title'])
                    item['content_html'] += utils.add_image(slide['params']['sizes']['original']['url'].replace('rawImage', '1000x0'), slide['params']['byline'])
                    item['content_html'] += '<p>{}</p>'.format(slide['params']['caption']['html2'])
            else:
                item['content_html'] += render_content(content)
    else:
        gallery_html = ''
        for content in content_json['body']:
            if content['type'] == 'gallery':
                gallery_html += render_content(content)
            elif content['type'] == 'factbox':
                item['content_html'] += utils.add_blockquote('<h3 style="margin-top:0;">{}</h3>{}'.format(content_json['factbox']['header'], content_json['factbox']['html1']))
            elif content['type'] == 'relatedStories':
                item['content_html'] += '<h3 style="margin-bottom:0;">Related stories:</h3><ul style="margin-top:0;">'
                for it in content_json['relatedStories']['items']:
                    item['content_html'] += '<li><a href="{}">{}</a></li>'.format(it['url'], it['title'])
                item['content_html'] += '</ul>'
            else:
                item['content_html'] += render_content(content)
        if gallery_html:
            item['content_html'] += '<hr/>' + gallery_html

    item['content_html'] = re.sub(r'</figure><(figure|table)', r'</figure><br/><\1', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if '/feed/' in args['url']:
        # https://www.sfgate.com/rss/
        # https://www.seattlepi.com/local/feed/seattlepi-com-Local-News-218.php
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(args['url'])
    paths = list(filter(None, split_url.path.split('/')))
    tld = tldextract.extract(args['url'])

    page_html = utils.get_url_html(args['url'])
    if not page_html:
        return None
    soup = BeautifulSoup(page_html, 'html.parser')
    article_urls = []
    for el in soup.find_all('a', attrs={"data-hdn-analytics": re.compile(r'visit\|article-')}) + soup.find_all('a', class_=re.compile(r'headline')):
        if paths and paths[0] != 'author' and paths[0] not in el['href'].split('/'):
            logger.debug('skipping different section content for ' + el['href'])
            continue
        if el['href'].startswith('/'):
            url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, el['href'])
        else:
            url = el['href']
            if tldextract.extract(url).domain != tld.domain:
                logger.debug('skipping external content for ' + url)
                continue
        if url not in article_urls:
            article_urls.append(url)

    n = 0
    feed_items = []
    for url in article_urls:
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)
                n += 1
                if 'max' in args and n == int(args['max']):
                    break

    feed = utils.init_jsonfeed(args)
    feed['title'] = soup.title.get_text()
    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed
