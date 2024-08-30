import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src):
    return re.sub(r'_\d+\.', '_992.', img_src)


def add_video(video_id, poster='', embed=True, save_debug=False):
    # optionally add &format=mp4
    video_url = 'https://abcnews.go.com/video/itemfeed?id={}'.format(video_id)
    video_json = utils.get_url_json(video_url)
    if not video_json:
        return ''
    if save_debug:
        utils.write_file(video_json, './debug/video.json')

    video = next((it for it in video_json['channel']['item']['media-group']['media-content'] if '@attributes' in it and it['@attributes']['type'] == 'application/x-mpegURL'), None)
    if not video:
        video = next((it for it in video_json['channel']['item']['media-group']['media-content'] if '@attributes' in it and it['@attributes']['type'] == 'video/mp4'), None)
        if not video:
            logger.warning('unhandled video format in ' + video_url)
            return ''

    if not poster:
        poster = video_json['channel']['item']['thumb']

    title = video_json['channel']['item']['media-group'].get('media-title')
    desc = video_json['channel']['item']['media-group'].get('media-description')
    if embed:
        if title:
            caption = title.strip()
        elif desc:
            caption = desc.strip()
        else:
            caption = ''
        video_html = utils.add_video(video['@attributes']['url'], video['@attributes']['type'], poster, caption, use_videojs=True)
    else:
        video_html = utils.add_video(video['@attributes']['url'], video['@attributes']['type'], poster, use_videojs=True)
        if title:
            video_html += '<h3>{}</h3>'.format(title.strip())
        if desc:
            video_html += '<p>{}</p>'.format(desc.strip())
    return video_html


def get_item(content_json, content_id, args, site_json, save_debug):
    if save_debug:
        utils.write_file(content_json, './debug/debug.json')

    item = {}
    item['id'] = content_id

    if content_json.get('id'):
        item_content = content_json
    elif content_json.get('items'):
        item_content = content_json['items'][0]
    else:
        item_content = {}

    beta_json = utils.get_url_json('https://abcnews.go.com/beta/json/article?id={}&showNewsFeed=false&analytics=false'.format(content_id))
    if beta_json:
        if save_debug:
            utils.write_file(beta_json, './debug/beta.json')
        beta_content = beta_json['content']
        item['url'] = beta_json['meta']['canonical']
        item['title'] = beta_content['headline']
    else:
        beta_content = {}
        item['url'] = item_content['link']
        item['title'] = item_content['title']

    if item_content.get('pubDate'):
        dt = datetime.strptime(item_content['pubDate'], '%m/%d/%Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    if item_content.get('lastModDate'):
        dt = datetime.strptime(item_content['lastModDate'], '%m/%d/%Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    item['authors'] = []
    if beta_content.get('byline'):
        item['author'] = {
            "name": re.sub(r'^By ', '', beta_content['byline'], flags=re.I)
        }
        item['authors'].append(item['author'])
    elif item_content.get('abcn:authors'):
        for author in item_content['abcn:authors']:
            if author['abcn:author'].get('abcn:author-name'):
                if isinstance(author['abcn:author']['abcn:author-name'], dict):
                    name = author['abcn:author']['abcn:author-name']['name'].strip()
                else:
                    name = author['abcn:author']['abcn:author-name'].strip()
                item['authors'].append({"name": name.title()})
            elif author['abcn:author'].get('abcn:author-provider'):
                if isinstance(author['abcn:author']['abcn:author-provider'], dict):
                    name = author['abcn:author']['abcn:author-provider']['name'].strip()
                else:
                    name = author['abcn:author']['abcn:author-provider'].strip()
                item['authors'].append({"name": name.title()})
        if len(item['authors']) > 0:
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }
    if 'author' not in item:
        if item_content.get('byline'):
            item['author'] = {
                "name": item_content['byline'].strip()
            }
        else:
            item['author'] = {
                "name": "ABCNews"
            }
        item['authors'].append(item['author'])

    item['tags'] = []
    if beta_content.get('keywords'):
        item['tags'] = [tag.strip() for tag in beta_content['keywords'].split(',')]
    else:
        item['tags'].append(item_content['abcn:section'])

    if beta_content.get('image'):
        item['image'] = resize_image(beta_content['image'])
    elif content_json.get('abcn:images'):
        item['image'] = resize_image(item_content['abcn:images'][0]['abcn:image']['url'])

    if beta_content.get('description'):
        item['summary'] = beta_content['description']
    elif content_json.get('abcn:subtitle'):
        item['summary'] = item_content['abcn:subtitle']

    item['content_html'] = ''

    if '/video/' in item['url']:
        if 'embed' in args:
            embed = True
        else:
            embed = False
        item['content_html'] = add_video(item_content['abcn:videos'][0]['abcn:video']['videoId'], embed=embed, save_debug=save_debug)
        return item

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if item_content['abcn:contentType'] == 'imagemaster':
        for i, it in enumerate(content_json['items']):
            image = it['abcn:images'][0]['abcn:image']
            desc = image.get('imagecaption').strip()
            if desc:
                if i == 0:
                    m = re.search(r'(.+)\s*</?br></?br>\s*(.+)', desc)
                    if m:
                        item['content_html'] += '<p><em>{}</em></p>'.format(m.group(1))
                        desc = m.group(2)
                desc = '<p>{}</p>'.format(desc)
            item['content_html'] += utils.add_image(resize_image(image['url']), image.get('imagecredit').strip(), desc=desc) + '<br/>'
        return item

    if item.get('summary'):
        item['content_html'] += '<p><em>{}</em></p>'.format(item['summary'])

    lead_video = ''
    if item_content.get('abcn:videos'):
        lead_video = add_video(item_content['abcn:videos'][0]['abcn:video']['videoId'], save_debug=save_debug)

    if lead_video:
        item['content_html'] += lead_video
    elif item_content.get('abcn:images'):
        image = item_content['abcn:images'][0]['abcn:image']
        captions = []
        caption = image.get('imagecaption').strip()
        if caption:
            captions.append(caption)
        caption = image.get('imagecredit').strip()
        if caption:
            captions.append(caption)
        item['content_html'] += utils.add_image(resize_image(image['url']), ' | '.join(captions))

    if item_content.get('description'):
        content_html = item_content['description'].replace('</div>>', '</div>')
        content_html = re.sub(r'</p>([A-Z0-9\W\s]+?)<p>', r'</p><h3>\1</h3><p>', content_html)
        content_soup = BeautifulSoup(content_html, 'html.parser')

        for el in content_soup.find_all(class_='e_image'):
            img_src = resize_image(el.img['src'])
            captions = []
            it = el.find(class_='e_image_sub_caption')
            if it:
                caption = it.get_text().strip()
                if caption:
                    captions.append(caption)
            it = el.find(class_='e_image_credit')
            if it:
                caption = it.get_text().strip()
                if caption:
                    captions.append(caption)
            new_html = utils.add_image(img_src, ' | '.join(captions))
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

        for el in content_soup.find_all(class_='t_markup'):
            embed_url = ''
            if el.find(class_='twitter-tweet'):
                links = el.blockquote.find_all('a')
                embed_url = links[-1]['href']
            elif el.find(class_='instagram-media'):
                embed_url = el.blockquote['data-instgrm-permalink']
            elif el.find(class_='tiktok-embed'):
                embed_url = el.blockquote['cite']
            elif el.iframe:
                embed_url = el.iframe['src']
            if embed_url:
                new_html = utils.add_embed(embed_url)
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()

        for el in content_soup.find_all('script'):
            el.decompose()

        item['content_html'] += str(content_soup)

    return item


def get_content(url, args, site_json, save_debug):
    if '/widgets/' in url:
        return None

    m = re.search(r'id=(\d+)|-(\d+)/image-|-(\d+)$|/embed/(\d+)|-(\d+)\?|-(\d+)$', url)
    if not m:

        logger.warning('unable to parse id from ' + url)
        return None

    content_id = list(filter(None, m.groups()))[0]
    content_json = utils.get_url_json('https://abcnews.go.com/rsidxfeed/{}/json'.format(content_id))
    if not content_json:
        return None

    return get_item(content_json['channels'][0], content_id, args, site_json, save_debug)


def get_feed(url, args, site_json, save_debug):
    split_url = urlsplit(args['url'])
    if not split_url.path or split_url.path == '/':
        feed_url = 'https://abcnews.go.com/rsidxfeed/homepage/json'
    else:
        feed_url = 'https://abcnews.go.com/rsidxfeed/section/{}/json'.format(split_url.path.split('/')[1])
    section_feed = utils.get_url_json(feed_url)
    if not section_feed:
        return None
    if save_debug:
        utils.write_file(section_feed, './debug/feed.json')

    n = 0
    items = []
    for channel in section_feed['channels']:
        if channel['subType'] == 'BANNER_AD':
            continue
        for content in channel['items']:
            if '/Live/video/' in content['link'] or '/widgets/' in content['link'] or 'story' in content['link'] or 'Story' in content['link']:
                logger.debug('skipping ' + content['link'])
                continue
            if save_debug:
                logger.debug('getting content from ' + content['link'])
            item = get_item(content, content['id'], args, site_json, save_debug)
            if item:
                if utils.filter_item(item, args) == True:
                    items.append(item)
                    n += 1
                    if 'max' in args:
                        if n == int(args['max']):
                            break

    # sort by date
    items = sorted(items, key=lambda i: i['_timestamp'], reverse=True)

    feed = utils.init_jsonfeed(args)
    feed['items'] = items.copy()
    return feed
