import json, math, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime, timezone

import utils
from feedhandlers import rss

import logging
logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    if '/web-stories/' in url:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        page_soup = BeautifulSoup(page_html, 'lxml')
        for el in page_soup.find_all('script', attrs={"type": "application/ld+json"}):
            ld_json = json.loads(el.string.replace('\n', ''))
            if ld_json.get('@type') and ld_json['@type'] == 'NewsArticle':
                break
            else:
                ld_json = None
        if not ld_json:
            logger.warning('unable to find ld+json in ' + url)
            return None
        if save_debug:
            utils.write_file(ld_json, './debug/debug.json')
        item = {}
        m = re.search(r'-(\d+)/?$', ld_json['url'])
        if m:
            item['id'] = m.group(1)
        else:
            item['id'] = ld_json['mainEntityOfPage']['@id']
        item['url'] = ld_json['url']
        item['title'] = ld_json['headline'].encode('latin1').decode('utf-8')
        dt = dateutil.parser.parse(ld_json['datePublished']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        if ld_json.get('dateModified'):
            dt = dateutil.parser.parse(ld_json['dateModified']).astimezone(timezone.utc)
            item['date_modified'] = dt.isoformat()
        if ld_json.get('author'):
            item['author'] = {
                "name": ld_json['author']['name']
            }
        elif ld_json.get('publisher'):
            item['author'] = {
                "name": ld_json['publisher']['name']
            }
        else:
            item['author'] = {
                "name": "News18.com"
            }
        item['authors'] = []
        item['authors'].append(item['author'])
        if ld_json.get('keywords'):
            item['tags'] = [it.strip() for it in ld_json['keywords'].split(',')]
        if ld_json.get('image'):
            item['image'] = ld_json['image']
        elif ld_json.get('associatedMedia') and ld_json['associatedMedia']['@type'] == 'ImageObject':
            item['image'] = ld_json['associatedMedia']['url']
        if ld_json.get('description'):
            item['summary'] = ld_json['description']
        if 'embed' in args:
            item['content_html'] = utils.format_embed_preview(item)
            return item
        item['content_html'] = ''
        for el in page_soup.find_all('amp-story-page'):
            it = el.find('amp-img')
            if it:
                if it.get('srcSet'):
                    img_src = utils.image_from_srcset(it['srcSet'])
                else:
                    img_src = it['src']
                caption = ''
                for it in el.select('.text-wrapper > span > span'):
                    caption += it.get_text().strip()
                caption = caption.encode('latin1').decode('utf-8')
                if re.search(r'^Next(:|$)', caption, flags=re.I):
                    continue
                item['content_html'] += utils.add_image(img_src)
                item['content_html'] += '<p>' + caption + '</p><div>&nbsp;</div>'
        return item

    m = re.search(r'-(\d+)\.html', url)
    if not m:
        logger.warning('unable to determine article id from ' + url)
        return None

    api_url = 'https://api-en.news18.com/nodeapi/v1/eng/get-article?article_id=' + m.group(1)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')
    data_json = api_json['data']

    item = {}
    item['id'] = data_json['story_id']
    item['url'] = data_json['weburl']
    item['title'] = data_json['display_headline']

    dt = datetime.fromisoformat(data_json['created_at']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if data_json.get('updated_at'):
        dt = datetime.fromisoformat(data_json['updated_at']).replace(tzinfo=timezone.utc)
        item['date_modified'] = dt.isoformat()

    if data_json.get('author_byline'):
        item['authors'] = []
        item['authors'] = [{"name": x['english_name']} for x in data_json['author_byline'] if x.get('english_name')]
        if len(item['authors']):
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }
    else:
        if data_json.get('author') and data_json['author'].get('name'):
            item['author'] = {
                "name": data_json['author']['name']
            }
        elif data_json.get('byline'):
            item['author'] = {
                "name": data_json['byline']
            }
        elif data_json.get('publish_by') and data_json['publish_by'].get('name'):
            item['author'] = {
                "name": data_json['publish_by']['name']
            }
        else:
            item['author'] = {
                "name": "News18.com"
            }
        item['authors'] = []
        item['authors'].append(item['author'])
    if data_json.get('edited_by') and data_json['edited_by'].get('name'):
        item['authors'].append(data_json['edited_by']['name'] + ' (editor)')
        item['author']['name'] += ' (Edited by ' + data_json['edited_by']['name'] + ')'

    item['tags'] = []
    if data_json.get('categories'):
        for it in data_json['categories']:
            item['tags'].append(it['name'])
    if data_json.get('tags'):
        for it in data_json['tags']:
            item['tags'].append(it['name'])
    if len(item['tags']) == 0:
        del item['tags']

    item['content_html'] = ''
    if data_json.get('intro'):
        item['summary'] = data_json['intro']
        item['content_html'] += '<p><em>' + data_json['intro'] + '</em></p>'
    elif data_json.get('meta_description'):
        item['summary'] = data_json['meta_description']

    if data_json.get('youtubeid'):
        item['content_html'] += utils.add_embed('https://www.youtube.com/watch?v=' + data_json['youtubeid'])
        if item['author']['name'] == 'News18.com' and data_json.get('auto_youtube_import') and data_json['auto_youtube_import'].get('nw_auto_yt_feed_channel_name'):
            item['author'] = {
                "name": data_json['auto_youtube_import']['nw_auto_yt_feed_channel_name']
            }
            item['authors'] = []
            item['authors'].append(item['author'])

    if data_json.get('images_all_sizes'):
        item['image'] = data_json['images_all_sizes']['sizes']['16x9']['url']
        if not data_json.get('youtubeid'):
            item['content_html'] += utils.add_image(item['image'], data_json['images_all_sizes'].get('caption'))
    elif data_json.get('images'):
        item['image'] = data_json['images']['url']
        if not data_json.get('youtubeid'):
            item['content_html'] += utils.add_image(item['image'], data_json['images'].get('caption'))

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    if data_json.get('movie_review') and data_json['movie_review'].get('movie_name'):
        item['content_html'] += '<div>&nbsp;</div><div style="text-align:center; font-size:1.5em; font-weight:bold;">' + data_json['movie_review']['movie_name'] + '</div>'
        if data_json['movie_review'].get('movie_rating'):
            item['content_html'] += utils.add_stars(float(data_json['movie_review']['movie_rating']))
        item['content_html'] += '<ul>'
        if data_json['movie_review'].get('movie_release_date'):
            dt = datetime.fromisoformat(data_json['movie_review']['movie_release_date']).replace(tzinfo=timezone.utc)
            item['content_html'] += '<li>Release date: ' + utils.format_display_date(dt, date_only=True) + '</li>'
        if data_json['movie_review'].get('movie_runtime'):
            item['content_html'] += '<li>Run time: {} hr, {} min</li>'.format(int(data_json['movie_review']['movie_runtime'].split(':')[0]), int(data_json['movie_review']['movie_runtime'].split(':')[1]))
        if data_json['movie_review'].get('movie_genre'):
            item['content_html'] += '<li>Genre: ' + data_json['movie_review']['movie_genre'] + '</li>'
        if data_json['movie_review'].get('star_cast'):
            item['content_html'] += '<li>Staring: ' + data_json['movie_review']['star_cast'] + '</li>'
        if data_json['movie_review'].get('director'):
            item['content_html'] += '<li>Director: ' + data_json['movie_review']['director'] + '</li>'
        if data_json['movie_review'].get('ott_platform'):
            item['content_html'] += '<li>Platform: ' + data_json['movie_review']['ott_platform'] + '</li>'
        item['content_html'] += '</ul><div>&nbsp;</div><hr><div>&nbsp;</div>'

    body_html = ''
    if data_json.get('body'):
        body_html += data_json['body']

    if '-liveblog' in item['url']:
        liveblog_json = utils.get_url_json('https://api-en.news18.com/nodeapi/v1/eng/get-liveblog?storyId={}'.format(item['id']))
        if liveblog_json:
            body_html += '<h2>Live Blog Posts:</h2>'
            for post in liveblog_json['data']['posts']:
                dt = datetime.fromisoformat(data_json['updated_at']).replace(tzinfo=timezone.utc)
                body_html += '<div style="font-size:0.8em;">' + utils.format_display_date(dt) + '</div>'
                body_html += '<div style="font-size:1.1em; font-weight:bold;">' + post['blog_title'] + '</div>'
                body_html += post['blog_content'] + '<div>&nbsp;</div><hr><div>&nbsp;</div>'

    if body_html:
        body = BeautifulSoup(body_html, 'html.parser')
        for el in body.select('p br'):
            el.insert_after(body.new_tag('br'))

        for el in body.find_all('figure', class_='wp-caption'):
            if el.figcaption:
                caption = el.figcaption.decode_contents()
            else:
                caption = ''
            new_html = utils.add_image(el.img['src'], caption)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)

        for el in body.find_all('blockquote', class_='twitter-tweet'):
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
            it = body.find('script', src=re.compile(r'twitter\.com'))
            if it:
                it.decompose()

        for el in body.find_all('blockquote', class_='instagram-media'):
            new_html = utils.add_embed(el['data-instgrm-permalink'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
            it = body.find('script', src=re.compile(r'instagram\.com'))
            if it:
                it.decompose()

        item['content_html'] += str(body)

    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
