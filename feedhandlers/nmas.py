import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    if 'programas' in paths:
        page_html = utils.get_url_html(url)
        if not page_html:
            return None
        soup = BeautifulSoup(page_html, 'lxml')
        ld_json = None
        for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
            ld_json = json.loads(el.string)
            if isinstance(ld_json, dict) and ld_json.get('@type') == 'VideoObject':
                break
            ld_json = None
        if not ld_json:
            logger.warning('unable to find ld+json VideoObject in ' + url)
            return None
        if save_debug:
            utils.write_file(ld_json, './debug/debug.json')
        item = {}
        item['id'] = split_url.path
        item['url'] = ld_json['url']
        item['title'] = ld_json['name']
        dt = datetime.fromisoformat(ld_json['uploadDate']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        item['author'] = {
            "name": ld_json['author']['name']
        }
        item['authors'] = []
        item['authors'].append(item['author'])
        item['tags'] = ld_json['keywords'].copy()
        item['image'] = ld_json['thumbnailUrl'][0]
        item['summary'] = ld_json['description']
        item['content_html'] = utils.add_video(ld_json['contentUrl'], 'application/x-mpegURL', item['image'], item['title'])
        if 'embed' not in args:
            item['content_html'] += '<p>' + item['summary'] + '</p>'
        return item

    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9,en-GB;q=0.8",
        "content-type": "application/json",
        "priority": "u=1, i",
        "sec-ch-ua": "\"Microsoft Edge\";v=\"135\", \"Not-A.Brand\";v=\"8\", \"Chromium\";v=\"135\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "x-secure-environment": "TfDyQ3sn%52dr8LV}&gxC;"
    }
    gql_data = {
        "operationName": "GetStoryPages",
        "variables": {
            "sectionPath": split_url.path
        },
        "query": "\n	query GetStoryPages($sectionPath: String!) {\n		getStoryPages(sectionPath: $sectionPath) {\n			title\n			editorialTitle\n			summary\n			author\n			cropType\n			path\n			published\n			dateTime\n			dateModified\n			changed\n			typeMedia\n			topic\n			metaData {\n				title\n				description\n				og_title\n				og_description\n				og_image\n				twitter_cards_description\n				twitter_cards_title\n			}\n			thumbnail {\n				imageUrl {\n					webp\n				}\n				imageDesktopUrl {\n					webp\n				}\n				alt\n				caption\n				height\n				width\n			}\n			images {\n				imageUrl {\n					webp\n					shapes {\n						rect\n						square\n						vertical\n						vintage\n						vintageVertical\n					}\n				}\n				alt\n				caption\n				width\n				height\n			}\n			videoStory {\n				cmsid\n				aspect\n				title\n				description\n				duration\n				path\n				topic\n				image {\n					imageUrl\n					imageAlt\n				}\n			}\n			relatedVideos {\n				cmsid\n				aspect\n				title\n				description\n				duration\n				date\n				path\n				topic\n				image {\n					imageUrl\n					imageAlt\n				}\n			}\n			adultContent\n			enhancement {\n				divAds\n				facebook\n				instagram\n				nmas\n				spotify\n				tiktok\n				twitter\n				youtube\n			}\n			term {\n				id\n				url\n				name\n			}\n			body\n			relationships {\n				field_block_custom {\n					data {\n						id\n						type\n					}\n				}\n			}\n			teads\n			seedTag\n		}\n	}\n"
    }
    gql_json = utils.post_url("https://apollo.nmas.com.mx/graphql", json_data=gql_data, headers=headers)
    if not gql_json:
        return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')
    story_json = gql_json['data']['getStoryPages']

    item = {}
    item['id'] = story_json['path']
    item['url'] = 'https://' + split_url.netloc + story_json['path']
    item['title'] = story_json['title']

    dt = datetime.fromisoformat(story_json['dateTime']).astimezone(timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    if story_json.get('dateModified'):
        dt = datetime.fromisoformat(story_json['dateModified']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    item['author'] = {
        "name": story_json['author']
    }
    item['authors'] = []
    item['authors'].append(item['author'])

    if story_json.get('term'):
        item['tags'] = [x['name'] for x in story_json['term']]

    item['content_html'] = ''
    if story_json.get('summary'):
        item['summary'] = story_json['summary']
        item['content_html'] += '<p><em>' + story_json['summary'] + '</em></p>'

    if story_json.get('thumbnail') and story_json['thumbnail'].get('imageUrl'):
        item['image'] = story_json['thumbnail']['imageUrl']['webp']
        item['content_html'] += utils.add_image(item['image'], story_json['thumbnail'].get('caption'))

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    soup = BeautifulSoup(story_json['body'], 'html.parser')
    for el in soup.find_all(class_='divAds'):
        el.decompose()

    for el in soup.find_all(id='teads-container'):
        el.decompose()

    for el in soup.find_all('lt-toolbar'):
        el.decompose()

    for el in soup.find_all(class_='nmas-image'):
        it = el.find_parent('figure', class_='caption')
        if it and it.figcaption:
            caption = it.figcaption.decode_contents()
        else:
            caption = ''
        new_html = utils.add_image(el['data-src'], caption)
        new_el = BeautifulSoup(new_html, 'html.parser')
        if it:
            it.replace_with(new_el)
        else:
            it = el.find_parent(class_='field')
            if it:
                it.replace_with(new_el)
            else:
                el.replace_with(new_el)

    for el in soup.find_all(class_='nMasVideo'):
        it = el.find_parent('figure', class_='caption')
        if it and it.figcaption:
            caption = it.figcaption.decode_contents()
        else:
            caption = el.get('data-title')
        new_html = utils.add_video(el['data-contenturl'], 'application/x-mpegURL', el.get('data-src'), caption)
        new_el = BeautifulSoup(new_html, 'html.parser')
        if it:
            it.replace_with(new_el)
        else:
            it = el.find_parent(class_='field')
            if it:
                it.replace_with(new_el)
            else:
                el.replace_with(new_el)

    for el in soup.find_all('blockquote', class_='twitter-tweet'):
        links = el.find_all('a')
        new_html = utils.add_embed(links[-1]['href'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        it = el.find_parent(class_='field')
        if it:
            it.replace_with(new_el)
        else:
            el.replace_with(new_el)

    for el in soup.find_all('iframe', recursive=False):
        new_html = utils.add_embed(el['src'])
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all('blockquote', class_=False):
        el['style'] = 'border-left:3px solid light-dark(#ccc,#333); margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.find_all(class_='wrapperTable'):
        el.table.attrs = {}
        el.table['style'] = 'width:90%; margin:auto; border-collapse:collapse; border-top:1px solid light-dark(#333,#ccc);'
        for it in el.find_all('tr'):
            it['style'] = 'border-bottom:1px solid light-dark(#333,#ccc);'
        for it in el.find_all('td'):
            it['style'] = 'padding:8px;'
        el.unwrap()

    for el in soup.find_all('blockquote', class_=False):
        el['style'] = 'border-left:3px solid light-dark(#ccc,#333); margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.find_all(class_=['media--type-twitter', 'media--type-image', 'media--type-n-videos']):
        el.decompose()

    for el in soup.find_all(class_=['field', 'media']):
        logger.warning('unhandled class {} in {}'.format(el['class'], item['url']))

    item['content_html'] += str(soup)
    return item
