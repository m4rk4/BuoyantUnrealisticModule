import pytz, re
from bs4 import BeautifulSoup, Comment
from datetime import datetime
from urllib.parse import urlsplit

from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1000):
    return '{}?w={}'.format(utils.clean_url(img_src), width)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path.split('/')))

    post_id = ''
    m = re.search(r'-lists/[^/]+-(\d+)', split_url.path)
    if m:
        post_id = m.group(1)
        post_type = 'pmc_list'
    else:
        m = re.search(r'-(\d+)$', paths[-1])
        if m:
            post_id = m.group(1)
            post_type = 'posts'
    if not post_id:
        logger.warning('unable to parse post id from ' + url)
        return None

    post_url = '{}/wp/v2/{}/{}'.format(site_json['wpjson_path'], post_type, post_id)
    post_json = utils.get_url_json(post_url)
    if post_json and save_debug:
        utils.write_file(post_json, './debug/post.json')

    article_url = '{}/mobile-apps/v1/article/{}'.format(site_json['wpjson_path'], post_id)
    article_json = utils.get_url_json(article_url)
    if not article_json:
        return None
    if save_debug:
        utils.write_file(article_json, './debug/debug.json')

    item = {}
    item['id'] = article_json['post-id']
    item['url'] = article_json['permalink']
    item['title'] = article_json['headline']

    tz_est = pytz.timezone('US/Eastern')
    dt_loc = datetime.fromisoformat(article_json['published-at'])
    dt_utc = tz_est.localize(dt_loc).astimezone(pytz.utc)
    item['date_published'] = dt_utc.isoformat()
    item['_timestamp'] = dt_utc.timestamp()
    item['_display_date'] = utils.format_display_date(dt_utc)

    dt_loc = datetime.fromisoformat(article_json['updated-at'])
    dt_utc = tz_est.localize(dt_loc).astimezone(pytz.utc)
    item['date_modified'] = dt_utc.isoformat()

    item['author'] = {}
    if article_json.get('byline'):
        item['author']['name'] = article_json['byline']
    elif post_json and post_json['_links'].get('author'):
        authors = []
        for link in post_json['_links']['author']:
            link_json = utils.get_url_json(link['href'])
            if link_json:
                authors.append(link_json['name'])
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

    item['tags'] = []
    for tag in article_json['tags']:
        item['tags'].append(tag['name'])

    item['summary'] = article_json['body-preview']

    lede = ''
    if article_json.get('featured-video'):
        if 'connatix_contextual_player' in article_json['featured-video']:
            m = re.search(r'playerId:"([^"]+)",mediaId:"([^"]+)"', re.sub(r'\s', '', article_json['featured-video']))
            if m:
                video_src = 'https://vid.connatix.com/pid-{}/{}/playlist.m3u8'.format(m.group(1), m.group(2))
                poster = 'https://img.connatix.com/pid-{}/{}/1_th.jpg?width=1000&format=jpeg&quality=60'.format(m.group(1), m.group(2))
                caption = []
                if article_json.get('featured-image'):
                    if article_json['featured-image'].get('caption'):
                        caption.append(article_json['featured-image']['caption'])
                    if article_json['featured-image'].get('credit'):
                        caption.append(article_json['featured-image']['credit'])
                lede += utils.add_video(video_src, 'application/x-mpegURL', poster, ' | '.join(caption))
        else:
            lede += utils.add_embed(article_json['featured-video'])

    if article_json.get('featured-image'):
        for img in article_json['featured-image']['crops']:
            if img['name'] == 'full':
                item['_image'] = img['url']
                if not lede:
                    caption = []
                    if article_json['featured-image'].get('caption'):
                        caption.append(article_json['featured-image']['caption'])
                    elif img.get('caption'):
                        caption.append(img['caption'])
                    if article_json['featured-image'].get('credit'):
                        caption.append(article_json['featured-image']['credit'])
                    elif img.get('credit'):
                        caption.append(img['credit'])
                    lede += utils.add_image(resize_image(img['url']), ' | '.join(caption))
                break

    if article_json.get('tagline'):
        lede = '<p><i>{}</i></p>'.format(article_json['tagline']) + lede

    if article_json.get('review_meta') and article_json['review_meta'].get('rating'):
        lede += '<h3>{}<br/>{}<br/><span style="font-size:1.5em;">{} / {}</span></h3>'.format(
            article_json['review_meta']['title'], article_json['review_meta']['artist'], article_json['review_meta']['rating'],
            article_json['review_meta']['rating_out_of'])

    soup = BeautifulSoup(article_json['body'], 'html.parser')

    for el in soup.find_all(class_='lrv-u-text-transform-uppercase'):
        el.string = el.string.upper()
        el.unwrap()

    for el in soup.find_all(class_='pmc-not-a-paywall'):
        el.unwrap()

    for el in soup.find_all('p', class_='paragraph'):
        el.attrs = {}

    for el in soup.find_all(id=re.compile(r'attachment_\d+')):
        img = el.find('img')
        if img:
            if 'alignleft' in el['class']:
                img['style'] = 'float:left; margin-right:8px;'
                el.parent.insert_after(BeautifulSoup('<div style="clear:left;"></div>', 'html.parser'))
            else:
                captions = []
                it = el.find(class_='wp-caption-text')
                if it:
                    captions.append(it.get_text())
                it = el.find(class_='rs-image-credit')
                if it:
                    captions.append(it.get_text())
                new_html = utils.add_image(resize_image(el.img['src']), ' | '.join(captions))
                el.insert_after(BeautifulSoup(new_html, 'html.parser'))
                el.decompose()

    for el in soup.find_all(class_='post-content-image'):
        img = el.find('img')
        if img:
            if img.get('data-lazy-src'):
                img_src = img['data-lazy-src']
            else:
                img_src = img['src']
            captions = []
            it = el.find('cite')
            if it:
                captions.append(it.get_text())
                it.decompose()
            it = el.find('figcaption')
            if it:
                captions.insert(0, it.get_text())
            new_html = utils.add_image(resize_image(img_src), ' | '.join(captions))
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled post-content-image in ' + item['url'])

    for el in soup.find_all(class_='wp-block-embed'):
        new_html = ''
        it = el.find('iframe')
        if it:
            new_html = utils.add_embed(it['src'])
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled wp-block-embed in ' + item['url'])

    for el in soup.find_all('iframe'):
        new_html = utils.add_embed(el['src'])
        if el.parent.name == 'b':
            el.parent.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.parent.decompose()
        else:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in soup.find_all('blockquote', class_='pullquote'):
        new_html = utils.add_pullquote(el.decode_contents())
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in soup.find_all('script'):
        new_html = ''
        if el.get('id') and 'connatix_contextual_player' in el['id']:
            m = re.search(r'playerId:"([^"]+)",mediaId:"([^"]+)"', re.sub(r'\s', '', el.string))
            if m:
                video_src = 'https://vid.connatix.com/pid-{}/{}/playlist.m3u8'.format(m.group(1), m.group(2))
                poster = 'https://img.connatix.com/pid-{}/{}/1_th.jpg?width=1000&format=jpeg&quality=60'.format(m.group(1), m.group(2))
                new_html = utils.add_video(video_src, 'application/x-mpegURL', poster)
            else:
                logger.warning('unhandled connatix_contextual_player in ' + item['url'])
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            el.decompose()

    item['content_html'] = lede + str(soup)

    if post_json['type'] == 'pmc_list':
        n = len(post_json['meta']['pmc_list_order'])
        for i, list_id in enumerate(post_json['meta']['pmc_list_order']):
            list_item_url = '{}/wp/v2/pmc_list_item/{}'.format(site_json['wpjson_path'], list_id)
            list_item = utils.get_url_json(list_item_url)
            if list_item:
                if save_debug:
                    utils.write_file(list_item, './debug/list.json')
                item['content_html'] += '<div>&nbsp;</div><hr/><div>&nbsp;</div>'
                if list_item['meta'].get('_pmc_featured_video_override_data'):
                    item['content_html'] += utils.add_embed(list_item['meta']['_pmc_featured_video_override_data'])
                elif list_item['_links'].get('wp:featuredmedia'):
                    media_json = utils.get_url_json(list_item['_links']['wp:featuredmedia'][0]['href'])
                    if media_json:
                        if media_json['media_type'] == 'image':
                            img_src = None
                            images = []
                            for key, val in media_json['media_details']['sizes'].items():
                                if any(it in key for it in ['thumb', 'small', 'tiny', 'landscape', 'portrait', 'square', 'logo', 'footer', 'archive', 'column', 'author', 'sponsor', 'hero']):
                                    continue
                                images.append(val)
                            if images:
                                image = utils.closest_dict(images, 'width', 1000)
                                if image and image.get('source_url'):
                                    img_src = image['source_url']
                                elif image and image.get('url'):
                                    img_src = image['url']
                            else:
                                if media_json.get('soure_url'):
                                    img_src = media_json['source_url']
                            if img_src:
                                if media_json['caption'].get('rendered'):
                                    if media_json['caption']['rendered'].startswith('<p'):
                                        caption = BeautifulSoup(media_json['caption']['rendered'], 'html.parser').p.decode_contents().strip()
                                    else:
                                        caption = BeautifulSoup(media_json['caption']['rendered'], 'html.parser').get_text().strip()
                                else:
                                    caption = ''
                                item['content_html'] += utils.add_image(img_src, caption) + '<div>&nbsp;</div>'
                else:
                    logger.warning('unhandled list item featured media ' + list_item_url)
                if post_json['meta'].get('pmc_list_numbering'):
                    if post_json['meta']['pmc_list_numbering'] == 'none':
                        num = ''
                    elif post_json['meta']['pmc_list_numbering'] == 'desc':
                        num = '<span style="font-size:2.4em; font-weight:bold; line-height:1em; vertical-align:middle;">{} | </span>'.format(n - i)
                    else:
                        num = '<span style="font-size:2.4em; font-weight:bold; line-height:1em; vertical-align:middle;">{} | </span>'.format(i + 1)
                else:
                    num = ''
                item['content_html'] += '<div>{}<span style="font-size:1.2em; font-weight:bold; line-height:2em; vertical-align:middle;">{}</span></div>'.format(num, list_item['title']['rendered'])
                if list_item['meta'].get('pmc_list_item_description'):
                    item['content_html'] += '<div style="font-size:1.1em;">{}</div>'.format(list_item['meta']['pmc_list_item_description'])
                if list_item.get('content') and list_item['content'].get('rendered'):
                    li_soup = BeautifulSoup(list_item['content']['rendered'], 'html.parser')
                    for el in li_soup.find_all(text=lambda text: isinstance(text, Comment)):
                        el.extract()
                    for el in li_soup.find_all(class_='pmc-not-a-paywall'):
                        el.unwrap()
                    for el in li_soup.find_all('p', class_='paragraph'):
                        el.attrs = {}
                    for el in li_soup.find_all(class_='lrv-u-text-transform-uppercase'):
                        el.string = el.string.upper()
                        el.unwrap()
                    item['content_html'] += str(li_soup)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
