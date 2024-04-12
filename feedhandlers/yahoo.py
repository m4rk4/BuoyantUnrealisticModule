import json, re, requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, unquote_plus, urlsplit

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
    it = image_wrapper.find('a', class_='link')
    if it:
        link = it['href']
    else:
        link = ''
    return utils.add_image(get_full_image(img_src), caption, link=link)


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
    video_json = utils.get_url_json('https://video-api.yql.yahoo.com/v1/video/sapi/streams/{}?protocol=http&format=mp4,webm,m3u8'.format(video_id))
    if not video_json:
        return ''
    # utils.write_file(video_json, './debug/video.json')
    video = utils.closest_dict(video_json['query']['results']['mediaObj'][0]['streams'], 'height', 360)
    if not video:
        video = video_json['query']['results']['mediaObj'][0]['streams'][0]
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
    clean_url = utils.clean_url(url)
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
        caas_json = None
        if 'www.autoblog.com' not in url:
            caas_url = 'https://www.yahoo.com/caas/content/article/?url=' + quote_plus(clean_url)
            caas_json = utils.get_url_json(caas_url, headers=headers)
        if not caas_json:
            m = re.search(r'"pstaid":"([^"]+)"', article_html)
            if not m:
                m = re.search(r'pstaid:\s*\'([^\']+)\'', article_html)
                if not m:
                    m = re.search(r'data-post-uuid="([^"]+)"', article_html)
                    if not m:
                        logger.warning('unable to find post-id in ' + url)
                        return None
            caas_url = 'https://www.yahoo.com/caas/content/article/?uuid=' + m.group(1)
            caas_json = utils.get_url_json(caas_url, headers=headers)
            if not caas_json:
                return None
        # utils.write_file(caas_json, './debug/debug.json')
        if caas_json.get('redirectRequestUUID'):
            caas_url = 'https://www.yahoo.com/caas/content/article/?uuid=' + caas_json['redirectRequestUUID']
            caas_json = utils.get_url_json(caas_url, headers=headers)
            if not caas_json:
                return None
        if not re.search(r'caas-3p-blocked', caas_json['items'][0]['markup']):
            break

    if save_debug:
        utils.write_file(article_html, './debug/debug.html')
        utils.write_file(caas_json, './debug/debug.json')

    if re.search(r'caas-3p-blocked', caas_json['items'][0]['markup']):
        logger.warning('caas-3p-blocked content in ' + url)

    article_json = caas_json['items'][0]['schema']['default']
    data_json = caas_json['items'][0]['data']['partnerData']

    item = {}
    item['id'] = data_json['uuid']

    if data_json.get('canonicalUrl'):
        item['url'] = data_json['canonicalUrl']
    elif data_json.get('hrefLangs'):
        link = next((it for it in data_json['hrefLangs'] if it['rel'] == 'canonical'), None)
        if link:
            item['url'] = link['href']
    if not item.get('url'):
        if article_json.get('mainEntityOfPage'):
            item['url'] = article_json['mainEntityOfPage']
        elif data_json.get('url'):
            item['url'] = data_json['url']
        else:
            item['url'] = url

    item['title'] = article_json['headline']

    dt = datetime.fromisoformat(article_json['datePublished'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(article_json['dateModified'].replace('Z', '+00:00'))
    item['date_modified'] = dt.isoformat()

    item['author'] = {}
    item['author']['name'] = article_json['author']['name']
    if data_json.get('providerBrand') and data_json['providerBrand'].get('displayName') and data_json['providerBrand']['displayName'] not in item['author']['name'] and data_json['providerBrand']['brandId'] not in item['url']:
        item['author']['name'] += ' ({})'.format(data_json['providerBrand']['displayName'])

    item['tags'] = article_json['keywords'].copy()

    item['_image'] = article_json['image']['url']

    item['summary'] = article_json['description']

    if 'embed' in args:
        item['content_html'] = '<div style="width:80%; margin-right:auto; margin-left:auto; border:1px solid black; border-radius:10px;">'
        if item.get('_image'):
            item['content_html'] += '<a href="{}"><img src="{}" style="width:100%; border-top-left-radius:10px; border-top-right-radius:10px;" /></a>'.format(item['url'], item['_image'])
        item['content_html'] += '<div style="margin:8px 8px 0 8px;"><div style="font-size:0.8em;">{}</div><div style="font-weight:bold;"><a href="{}">{}</a></div>'.format(urlsplit(item['url']).netloc, item['url'], item['title'])
        if item.get('summary'):
            item['content_html'] += '<p style="font-size:0.9em;">{}</p>'.format(item['summary'])
        item['content_html'] += '<p><a href="{}/content?read&url={}">Read</a></p></div></div>'.format(config.server, quote_plus(item['url']))
        return item

    caas_soup = BeautifulSoup(caas_json['items'][0]['markup'], 'html.parser')
    caas_body = caas_soup.find(class_='caas-body')
    # utils.write_file(str(caas_body), './debug/debug.html')

    for el in caas_body.find_all('figure'):
        new_html = get_image(el)
        if new_html:
            if re.search(r'https://www\.autoblog\.com/cars-for-sale/', new_html):
                # Ad
                el.decompose()
            else:
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
            quote += it.decode_contents()
        if re.search(r'^["“].*["”]$', quote) and len(re.findall(r'["“"”]', quote)) == 2:
            new_html = utils.add_pullquote(quote[1:-1])
        else:
            new_html = utils.add_blockquote(quote)
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
        if 'quick-overview' in el['class']:
            el.decompose()
            continue
        new_html = ''
        it = el.find(class_='overview-label')
        if it:
            new_html += '<h3>{}</h3>'.format(it.get_text().strip())
        for it in el.find_all(class_='list-item'):
            new_html = '<div style="width:90%; margin:auto; padding:8px; border:1px solid black; border-radius:10px;"><div style="display:flex; flex-wrap:wrap; gap:1em;">'
            info = el.find(class_=['edit-label', 'editor-label'])
            if info:
                new_html += '<div style="flex:0 0 100%;"><span style="color:#9a58b5;; font-weight:bold;">{}</span></div>'.format(info.get_text().strip())
            info = it.find(class_='img-container')
            if info:
                img = info.find('img')
                if img:
                    img_src = ''
                    if img.get('data-src'):
                        img_src = img['data-src']
                    elif img.get('src'):
                        img_src = img['src']
                    if img_src:
                        if info.a:
                            new_html += '<div style="flex:1; min-width:256px; margin:auto;"><a href="{}"><img src="{}" style="width:100%" /></a></div>'.format(utils.get_redirect_url(info.a['href']), img_src)
                        else:
                            new_html += '<div style="flex:1; min-width:256px; margin:auto;"><img src="{}" style="width:100%" /></div>'.format(img_src)
            new_html += '<div style="flex:2; min-width:256px; margin:auto;">'
            info = it.find(class_=['list-info', 'info-data'])
            if info:
                info_name = info.find(class_='product-name')
                if info_name:
                    if info_name.a:
                        new_html += '<div><a href="{}"><span style="font-size:1.2em; font-weight:bold">{}</span></a></div>'.format(utils.get_redirect_url(info_name.a['href']), info_name.get_text())
                    else:
                        new_html += '<div><span style="font-size:1.2em; font-weight:bold">{}</span></div>'.format(info_name.get_text())
            sib = it.find_next_sibling()
            if sib and sib.get('class') and 'bottom-info' in sib['class']:
                info = sib.find(class_='desc')
                if info:
                    new_html += '<p><small>{}</small></p>'.format(info.get_text())
                for info in sib.find_all(class_='cta-btn'):
                    new_html += '<div style="margin-top:0.8em; margin-bottom:0.8em; text-align:center;"><a href="{}"><span style="display:inline-block; min-width:8em; color:white; background-color:#9a58b5; padding:0.5em;">{}</span></a></div>'.format(utils.get_redirect_url(info['href']), info.get_text())
            else:
                info = it.find(class_='desc')
                if info:
                    new_html += '<p><small>{}</small></p>'.format(info.get_text())
                for info in it.find_all(class_='cta-btn'):
                    new_html += '<div style="margin-top:0.8em; margin-bottom:0.8em; text-align:center;"><a href="{}"><span style="display:inline-block; min-width:8em; color:white; background-color:#9a58b5; padding:0.5em;">{}</span></a></div>'.format(utils.get_redirect_url(info['href']), info.get_text())
            new_html += '</div></div>'
            if it.find(class_='commerce-score'):
                new_html += '<div style="font-weight:bold; text-align:center; padding-bottom:8px;">'
                score = it.find(class_='commerce-score-val')
                if score:
                    new_html += '<span style="font-size:2em; line-height:1em; vertical-align:middle;">{}</span>'.format(
                        score.get_text())
                score = it.find(class_='commerce-score-total')
                if score:
                    new_html += ' / ' + score.get_text()
                score = it.find(class_='commerce-score-text')
                if score:
                    new_html += ' ({})'.format(score.get_text())
                new_html += '</div>'
            info = el.find(class_='pros-cons')
            if info:
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:1em;">'
                for ul in info.find_all('ul'):
                    new_html += '<div style="flex:1; min-width:256px;"><div style="font-size:1.1em; font-weight:bold;">{}</div>{}</div>'.format(ul.find_previous_sibling(class_='title').get_text(), str(ul))
                new_html += '</div>'
            new_html += '</div><div>&nbsp;</div>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    gallery_html = ''
    for el in caas_body.find_all('a', attrs={"data-ylk": re.compile(r'Full Image Gallery', flags=re.I)}):
        page_html = utils.get_url_html(el['href'])
        if page_html:
            gallery_soup = BeautifulSoup(page_html, 'lxml')
            gallery_html += '<h2><a href="{}">{}</a></h2>'.format(el['href'], gallery_soup.title.get_text())
            for slide in gallery_soup.find_all(class_='splide__slide'):
                if 'splide__default__slide' in slide['class'] or 'splide__thumbnail' in slide['class']:
                    continue
                img = slide.find('img')
                if img:
                    if img.get('data-splide-lazy'):
                        img_src = img['data-splide-lazy']
                    else:
                        img_src = img['src']
                    captions = []
                    it = slide.find(class_='splide__slide__content')
                    if it:
                        for li in it.find_all('li'):
                            captions.append(li.get_text())
                    gallery_html += utils.add_image(img_src, ' | '.join(captions))
            for it in caas_body.find_all('a', href=el['href']):
                if not it.get_text() and not it.find_parent('figure'):
                    parent = it.find_parent('p')
                    if parent:
                        parent.decompose()
            parent = el.find_parent('p')
            if parent:
                parent.decompose()

    for el in caas_body.find_all('ul', class_='caas-list-bullet'):
        it = el.find_previous_sibling()
        if it and re.search(r'Related\.\.\.|You Might Also Like|Most Read from', it.get_text()):
            it.decompose()
            el.decompose()

    for el in caas_body.find_all('a'):
        href = el.get('href')
        if href:
            el.attrs = {}
            if href.startswith('https://shopping.yahoo.com/'):
                el['href'] = utils.get_redirect_url(href)
            else:
                el['href'] = href

    for el in caas_body.find_all(class_='caas-readmore'):
        el.decompose()

    for el in caas_body.find_all('p', string=re.compile(r'^Read More:')):
        el.decompose()

    article_soup = BeautifulSoup(article_html, 'lxml')
    content_html = ''
    el = caas_soup.find(class_='caas-subheadline')
    if el:
        content_html += '<p><em>{}</em></p>'.format(el.get_text().strip())
    else:
        el = article_soup.find('h2', class_='subheadline')
        if el:
            content_html += '<p><em>{}</em></p>'.format(el.get_text().strip())

    el = caas_soup.find(class_=re.compile(r'caas-cover|caas-hero'))
    if el:
        if 'caas-figure' in el['class']:
            content_html += get_image(el)
        elif 'caas-carousel' in el['class']:
            # Slideshow - add lead image and remaining slides to end
            for i, slide in enumerate(el.find_all(class_='caas-carousel-slide')):
                gallery_html += '<h3>Gallery</h3>'
                new_html = get_image(slide)
                if new_html:
                    if i == 0:
                        content_html += new_html
                    gallery_html += new_html
        elif 'yvideo' in el['class']:
            content_html += get_video(el)
        elif 'caas-iframe' in el['class']:
            content_html += get_iframe(el)
        else:
            logger.debug('unhandled caas-cover element type with classes {}'.format(str(el['class'])))

    el = article_soup.find(attrs={"data-component": "ProsCons"})
    if el:
        for it in el.find_all('div', recursive=False):
            if it.find('ul'):
                content_html += '<h3>{}</h3><ul>'.format(it.h2.get_text())
                for li in it.find_all('li'):
                    content_html += '<li>{}</li>'.format(li.get_text())
                content_html += '</ul>'

    el = article_soup.find(attrs={"data-component": "ProductScores"})
    if el:
        for it in el.find_all('div'):
            score = it.get_text().strip()
            if score.isnumeric():
                content_html += '<h3>Review score: {}</h3>'.format(score)
                break

    for el in article_soup.find_all('ul', class_='vital-stats-list'):
        new_html = '<table>'
        for li in el.find_all('li'):
            it = li.find(class_='stat-title')
            if it:
                title = it.decode_contents()
            else:
                title = ''
            it = li.find(class_='vital-val')
            if it:
                val = it.decode_contents()
            else:
                val = ''
            new_html += '<tr><td>{}</td><td>{}</td></tr>'.format(title, val)
        new_html += '</table>'
        if caas_body.contents[0].name == 'figure':
            caas_body.contents[0].insert_after(BeautifulSoup(new_html, 'html.parser'))
        else:
            content_html += new_html

    content_html += caas_body.decode_contents() + gallery_html
    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', content_html)
    return item


def get_feed(url, args, site_json, save_debug=False):
    return rss.get_feed(url, args, site_json, save_debug, get_content)
