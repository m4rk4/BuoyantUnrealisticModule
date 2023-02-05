import json, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import unquote_plus

import config
from feedhandlers import rss
import utils

import logging

logger = logging.getLogger(__name__)


def get_full_image(img_src):
    m = re.search(r'(https:\/\/s\.yimg\.com\/os\/creatr-uploaded-images\/[^\.]+)', img_src)
    if m:
        return m.group(1)
    m = re.search(r'image_uri=([^&]+)', img_src)
    if m:
        return unquote_plus(m.group(1))
    return img_src


def get_image(image_wrapper):
    img = image_wrapper.find('img')
    if not img:
        return ''
    if img.get('src'):
        img_src = img['src']
    elif img.get('data-src'):
        img_src = img['data-src']
    else:
        logger.warning('unknown img src in ' + str(img))
        return ''
    caption = ''
    if img.get('alt'):
        caption = img['alt']
    else:
        figcap = image_wrapper.find('figcaption')
        if figcap:
            caption = figcap.get_text()
    return utils.add_image(get_full_image(img_src), caption)


def get_video(video_wrapper):
    yvideo = video_wrapper.find(class_='caas-yvideo')
    if not yvideo:
        return ''
    video_config = json.loads(yvideo['data-videoconfig'])
    if video_config.get('media_id_1'):
        video_id = video_config['media_id_1']
    elif video_config.get('playlist'):
        video_id = video_config['playlist']['mediaItems'][0]['id']
    else:
        logger.warning('unknown video id in ' + str(yvideo))
        return ''
    video_json = utils.get_url_json(
        'https://video-api.yql.yahoo.com/v1/video/sapi/streams/{}?protocol=http&format=mp4,webm,m3u8'.format(video_id))
    if not video_json:
        return ''
    utils.write_file(video_json, './debug/video.json')
    video = utils.closest_dict(video_json['query']['results']['mediaObj'][0]['streams'], 'height', 360)
    caption = []
    if video_json['query']['results']['mediaObj'][0]['meta'].get('title'):
        caption.append(video_json['query']['results']['mediaObj'][0]['meta']['title'])
    if video_json['query']['results']['mediaObj'][0]['meta'].get('attribution'):
        caption.append(video_json['query']['results']['mediaObj'][0]['meta']['attribution'])
    poster = video_json['query']['results']['mediaObj'][0]['meta']['thumbnail']
    return utils.add_video(video['host'] + video['path'], video['mime_type'], poster, ' | '.join(caption))


def get_iframe(iframe_wrapper):
    embed = iframe_wrapper.find('iframe')
    if not embed:
        embed = iframe_wrapper.find('blockquote')
    embed_src = ''
    if embed.get('src'):
        embed_src = embed['src']
    elif embed.get('data-src'):
        embed_src = embed['data-src']
    if not embed_src:
        return ''
    return utils.add_embed(embed_src)


def get_content(url, args, site_json, save_debug=False):
    for i in range(3):
        # Need to load the article page first to set appropriate cookies otherwise some embedded content is restricted
        # Sometimes need to do this multiple times
        s = utils.requests_retry_session()
        headers = config.default_headers
        s.headers.update(headers)
        r = s.get(url, headers=headers)
        if r.status_code != 200:
            return None
        cookies = []
        c = s.cookies.get_dict()
        for key, val in c.items():
            cookies.append('{}={}'.format(key, val))
        headers['cookie'] = '; '.join(cookies)
        article_html = r.text
        m = re.search(r'"pstaid":"([^"]+)"', article_html)
        if not m:
            logger.warning('unable to find post-id in ' + url)
            return None
        post_id = m.group(1)
        caas_url = 'https://www.yahoo.com/caas/content/article/?uuid=' + post_id
        caas_json = utils.get_url_json(caas_url, headers=headers)
        if not caas_json:
            return None
        if not re.search(r'caas-3p-blocked', caas_json['items'][0]['markup']):
            break

    if re.search(r'caas-3p-blocked', caas_json['items'][0]['markup']):
        logger.warning('caas-3p-blocked content in ' + url)

    if save_debug:
        utils.write_file(article_html, './debug/debug.html')
        utils.write_file(caas_json, './debug/debug.json')

    article_json = caas_json['items'][0]['schema']['default']
    item = {}
    item['id'] = post_id
    if article_json.get('mainEntityOfPage'):
        item['url'] = article_json['mainEntityOfPage']
    else:
        item['url'] = caas_json['items'][0]['data']['partnerData']['url']
    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['dateModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = article_json['author']['name']

    item['tags'] = article_json['keywords'].copy()

    item['_image'] = article_json['image']['url']

    item['summary'] = article_json['description']

    caas_soup = BeautifulSoup(caas_json['items'][0]['markup'], 'html.parser')
    caas_body = caas_soup.find(class_='caas-body')

    for el in caas_body.find_all('figure'):
        new_html = get_image(el)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in caas_body.find_all(class_='caas-carousel'):
        new_html = ''
        for slide in el.find_all(class_='caas-carousel-slide'):
            new_html += get_image(slide)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in caas_body.find_all(class_='caas-yvideo-wrapper'):
        new_html = get_video(el)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in caas_body.find_all(class_='caas-iframe-wrapper'):
        new_html = get_iframe(el)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in caas_body.find_all(class_='caas-iframe'):
        new_html = get_iframe(el)
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()

    for el in caas_body.find_all(class_='caas-pull-quote-wrapper'):
        logger.debug('caas-pull-quote-wrapper in ' + url)
        quote = ''
        for it in el.find_all('p'):
            if quote:
                quote += '<br/><br/>'
            quote += utils.bs_get_inner_html(it)
        new_html = utils.add_pullquote(quote)
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in caas_body.find_all(class_='twitter-tweet-wrapper'):
        tweet_urls = el.find_all('a')
        new_html = utils.add_embed(tweet_urls[-1]['href'])
        el.insert_after(BeautifulSoup(new_html, 'html.parser'))
        el.decompose()

    for el in caas_body.find_all(class_='instagram-media-wrapper'):
        if el.blockquote and el.blockquote.get('data-instgrm-permalink'):
            new_html = utils.add_embed(el.blockquote['data-instgrm-permalink'])
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled instagram-media-wrapper in ' + url)

    for el in caas_body.find_all(class_=['pd-list', 'mini-pd']):
        new_html = ''
        it = el.find(class_='overview-label')
        if it:
            new_html += '<h3>{}</h3>'.format(it.get_text().strip())
        for it in el.find_all(class_='list-item'):
            new_html += '<div>'
            links = it.find_all('a')
            link = utils.get_redirect_url(links[0]['href'])
            img = it.find('img')
            if img:
                img_src = ''
                if img.get('data-src'):
                    img_src = img['data-src']
                elif img.get('src'):
                    img_src = img['src']
                if img_src:
                    new_html += '<a href="{}"><img style="float:left; width:128px; margin-right:8px;" src="{}"/>'.format(link, img_src)
            new_html += '<div>'
            info = it.find(class_=['list-info', 'info-data'])
            if info:
                new_html += '<a href="{}"><span style="font-size:1.2em; font-weight:bold">{}</span></a>'.format(link, info.h4.get_text())
            info = it.find(class_='desc')
            if info:
                new_html += '<br/><small>{}</small>'.format(info.get_text())
            new_html += '<br/><a href="{}">{}</a>'.format(link, links[-1].get_text())
            new_html += '</div><div style="clear:left;">&nbsp;</div></div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in caas_body.find_all('a'):
        href = el.get('href')
        if href:
            el.attrs = {}
            el['href'] = href

    for el in caas_body.find_all(class_='caas-readmore'):
        el.decompose()

    content_html = caas_body.decode_contents()

    article_soup = BeautifulSoup(article_html, 'lxml')
    el = article_soup.find(attrs={"data-component": "ProsCons"})
    if el:
        new_html = ''
        for it in el.find_all('div', recursive=False):
            if it.find('ul'):
                new_html += '<h3>{}</h3><ul>'.format(it.h2.get_text())
                for li in it.find_all('li'):
                    new_html += '<li>{}</li>'.format(li.get_text())
                new_html += '</ul>'
        content_html = new_html + content_html

    el = article_soup.find(attrs={"data-component": "ProductScores"})
    if el:
        for it in el.find_all('div'):
            score = it.get_text().strip()
            if score.isnumeric():
                content_html = '<h3>Review score: {}</h3>'.format(score) + content_html
                break

    el = caas_soup.find(class_=re.compile(r'caas-cover|caas-hero'))
    if el:
        if 'caas-figure' in el['class']:
            new_html = get_image(el)
            if new_html:
                content_html = new_html + content_html
        elif 'caas-carousel' in el['class']:
            # Slideshow - add lead image and remaining slides to end
            for i, slide in enumerate(el.find_all(class_='caas-carousel-slide')):
                content_html += '<h3>Gallery</h3>'
                new_html = get_image(slide)
                if new_html:
                    if i == 0:
                        content_html = new_html + content_html
                    content_html += new_html
        elif 'yvideo' in el['class']:
            new_html = get_video(el)
            if new_html:
                content_html = new_html + content_html
        elif 'caas-iframe' in el['class']:
            new_html = get_iframe(el)
            if new_html:
                content_html = new_html + content_html
        else:
            logger.debug('unhandled caas-cover element type with classes {}'.format(str(el['class'])))

    el = caas_soup.find(class_='caas-subheadline')
    if el:
        content_html = '<p><em>{}</em></p>'.format(el.get_text().strip()) + content_html

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><br/><\2', content_html)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
