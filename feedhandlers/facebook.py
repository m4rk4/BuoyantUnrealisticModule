import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit, quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)


def get_fb_html(fb_url, embed):
    split_url = urlsplit(fb_url)
    if '.php' not in fb_url:
        url = utils.clean_url(fb_url)
    else:
        url = fb_url
    headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
               "Accept-Encoding": "gzip",
               "Accept-Language": "en-US,en;q=0.9",
               "Cache-Control": "max-age=0",
               "Cookie": "wd=962x1097",
               "Host": split_url.netloc,
               "Referer": url,
               "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"102\", \"Google Chrome\";v=\"102\"",
               "sec-ch-ua-mobile": "?0",
               "sec-ch-ua-platform": "\"Windows\"",
               "sec-fetch-dest": "document",
               "sec-fetch-mode": "navigate",
               "sec-fetch-site": "none",
               "sec-fetch-user": "?1",
               "upgrade-insecure-requests": "1",
               "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.5005.63 Safari/537.36",
    }
    if embed:
        url = 'https://www.facebook.com/plugins/post.php?href={}&_fb_noscript=1'.format(quote_plus(url))
    return utils.get_url_html(url, headers=headers)


def get_full_photo(photo_url):
    img_src = ''
    page_html = get_fb_html(photo_url, True)
    if not page_html:
        return img_src
    soup = BeautifulSoup(page_html, 'html.parser')
    split_url = urlsplit(photo_url)
    for el in soup.body.find_all('a'):
        it = el.find('img')
        if it and split_url.path in el['href']:
            img_src = it['src']
            break
    return img_src


def get_next_photo(photo_url):
    next_url = ''
    img_src = ''
    page_html = get_fb_html(photo_url, False)
    if not page_html:
        return next_url, img_src
    m = re.search(r'"nodeID":"(\d+)"', page_html)
    if m:
        photo_id = m.group(1)
    else:
        paths = list(filter(None, urlsplit(photo_url).path.split('/')))
        photo_id = paths[-1]
    m = re.search(r'"prevMedia":({.*?}),"nextMedia"', page_html)
    if not m:
        utils.write_file(page_html, './debug/facebook.html')
        logger.warning('unable to find next media in ' + photo_url)
        return next_url, img_src
    next_media = json.loads(m.group(1))
    if len(next_media['edges']) == 0:
        return next_url, img_src
    if next_media['edges'][0]['node']['__typename'] != 'Photo':
        logger.warning('unhandled next media type {} in {}'.format(next_media['edges'][0]['node']['__typename'], photo_url))
        return next_url, img_src
    next_url = photo_url.replace(photo_id, next_media['edges'][0]['node']['id'])
    img_src = get_full_photo(next_url)
    return next_url, img_src


def format_post_message(post_message):
    for el in post_message.find_all(class_='text_exposed_hide'):
        el.decompose()
    for el in post_message.find_all(class_='text_exposed_show'):
        el.unwrap()
    for el in post_message.find_all(class_='text_exposed_root'):
        el.unwrap()
    for el in post_message.find_all('a'):
        if el['href'].startswith('/'):
            href = 'https://www.facebook.com' + el['href']
        else:
            href = el['href']
        el.attrs = {}
        if re.search(r'/hashtag/', href):
            el['href'] = utils.clean_url(href)
        else:
            el['href'] = utils.get_redirect_url(href)
    return post_message.decode_contents()


def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    query = parse_qs(split_url.query)
    if query.get('href'):
        fb_url = query['href'][0]
    else:
        fb_url = url.replace('graph.facebook.com', 'www.facebook.com')
    embed_html = get_fb_html(fb_url, True)
    if not embed_html:
        return None

    if save_debug:
        utils.write_file(embed_html, './debug/facebook.html')

    item = {}

    soup = BeautifulSoup(embed_html, 'html.parser')
    el = soup.find('div', attrs={"role": "feed"})
    if el and el.p:
        if re.search(r'no longer available', el.p.get_text()):
            item['content_html'] = '<blockquote><b>Embedded content from <a href="{0}">{0}</a></b><br/>{1}</blockquote>'.format(url, el.p.get_text())
            return item

    el = soup.find('a', href=re.compile(r'/sharer/sharer\.php'))
    if not el:
        logger.warning('unable to get content from ' + url)
        return None
    split_url = urlsplit('https://www.facebook.com' + el['href'].replace('&amp;', '&'))
    query = parse_qs(split_url.query)

    item['url'] = query['u'][0]
    item['id'] = item['url']

    el = soup.find(class_='timestamp')
    if el:
        if el.get('data-utime'):
            dt = datetime.fromtimestamp(int(el['data-utime'])).replace(tzinfo=timezone.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)
    else:
        item['_display_date'] = 'Date unknown'

    item['author'] = {}
    avatar = ''
    el = soup.find('img', attrs={"aria-label":True})
    if el:
        item['author']['name'] = el['aria-label']
        item['title'] = 'A Facebook post by ' + item['author']['name']
        avatar = '{}/image?url={}&height=48&mask=ellipse'.format(config.server, quote_plus(el['src']))
        it = el.find_previous('a')
        if it:
            item['author']['url'] = utils.clean_url(it['href'])
    if not item['author'].get('url') and '.php' not in item['url']:
        split_url = urlsplit(item['url'])
        paths = list(filter(None, split_url.path.split('/')))
        if not item['author'].get('name'):
            item['author']['name'] = re.sub(r'([a-z])([A-Z])', r'\1 \2', paths[0])
        item['author']['url'] = 'https://www.facebook.com/' + paths[0]
    if not avatar:
        avatar = '{}/image?height=48&mask=ellipse'.format(config.server)

    item['content_html'] = '<table style="width:500px; border:1px solid black; border-collapse:collapse;"><tr><td style="width:48px;"><img src="{}"/></td><td style="vertical-align:middle;"><a href="{}"><strong style="font-size:1.2em;">{}</strong></a><br/><small>{}</small></td></tr>'.format(avatar, item['author']['url'], item['author']['name'], item['_display_date'])

    media_html = ''
    for el in soup.body.find_all('a', href=re.compile(r'facebook\.com/photo\.php|/photos/')):
        it = el.find('img')
        if it:
            if it.get('alt') and it['alt'] == 'app-facebook':
                pass
            else:
                media_html += utils.add_image(it['src'], link=el['href']) + '<br/>'
    if media_html:
        item['content_html'] += '<tr><td colspan="2" style="padding:0.3em;">' + media_html[:-5] + '</td></tr>'

    media_html = ''
    for el in soup.body.find_all('video'):
        video_src = ''
        if el.get('src'):
            video_src = el['src']
        else:
            m = re.search(r'"sd_src_no_ratelimit":"([^"]+)"', embed_html)
            if m:
                video_src = m.group(1).replace('/\\', '/')
            else:
                m = re.search(r'"sd_src":"([^"]+)"', embed_html)
                if m:
                    video_src = m.group(1).replace('/\\', '/')
                else:
                    m = re.search(r'"hd_src":"([^"]+)"', embed_html)
                    if m:
                        video_src = m.group(1).replace('/\\', '/')
        if video_src:
            poster = ''
            it = el.find_next_sibling()
            if it:
                img = it.find('img')
                if img:
                    poster = img['src']
            if not poster:
                poster = '{}/image?url={}'.format(config.server, quote_plus(video_src))
            media_html += utils.add_video(video_src, 'video/mp4', poster)
        else:
            logger.warning('unknown video src in ' + item['url'])
    if media_html:
        item['content_html'] += '<tr><td colspan="2" style="padding:0.3em;">' + media_html + '</td></tr>'

    el = soup.body.find(class_='userContent')
    if el:
        post_message = format_post_message(el)
        item['content_html'] += '<tr><td colspan="2" style="padding:0.3em;">{}</td></tr>'.format(post_message)

    media_link = ''
    media_html = ''
    page_soup = None
    for i, el in enumerate(soup.body.find_all(class_='uiScaledImageContainer')):
        ld_json = None
        if el.parent:
            it = el.parent.find('script', attrs={"type": "application/ld+json"})
            if it:
                ld_json = json.loads(it.string)
        if ld_json:
            img_src = ld_json['image']['contentUrl']
            caption = ld_json['image']['caption']
            media_link = ld_json['url']
        else:
            img_src = ''
            caption = ''
            media_link = ''
            img = el.find('img')
            if img:
                img_src = img['src']
                img_path = urlsplit(img_src).path
                # This is usually a low quality photo.
                # Try to get the full size image from the photo page.
                if i == 0:
                    page_html = get_fb_html(item['url'], False)
                    if page_html:
                        if not re.search(r'/photos/', page_html):
                            logger.warning('trying ' + item['url'].replace('www.', 'm.'))
                            page_html = get_fb_html(item['url'].replace('www.', 'm.'), False)
                            if page_html:
                                page_soup = BeautifulSoup(page_html, 'html.parser')
                    if page_html and save_debug:
                        utils.write_file(page_html, './debug/debug.html')
                if page_html:
                    m = re.search(r'ajaxify="([^"]+)" data-ploi="([^"]+{}[^"]+)"'.format(img_path), page_html)
                    if m:
                        media_link = 'https://www.facebook.com' + urlsplit(m.group(1)).path + '?type=3'
                        img_src = m.group(2).replace('&amp;', '&')
                    elif page_soup:
                        for a in soup.body.find_all('a'):
                            print(a['href'])
                            it = a.find('img')
                            if it and img_path in it['src']:
                                media_link = 'https://www.facebook.com' + urlsplit(a['href']).path + '?type=3'
                                img_src = get_full_photo(media_link)
                                break
                    if not img_src:
                        logger.debug('unable to find full image src in ' + item['url'])
        if img_src:
            media_html += utils.add_image(img_src, caption, link=media_link) + '<br/>'

    if media_html and media_link:
        # check for more images (only works if we know the last image link)
        m = re.search(r'\+(\d+)', el.parent.get_text().strip())
        if m:
            n = int(m.group(1))
            next_url, img_src = get_next_photo(media_link)
            while img_src and n > 1:
                n = n - 1
                media_html += utils.add_image(img_src, link=next_url) + '<br/>'
                next_url, img_src = get_next_photo(next_url)

    if media_html:
        item['content_html'] += '<tr><td colspan="2" style="padding:0.3em;">' + media_html[:-5] + '</td></tr>'

    item['content_html'] += '<tr><td colspan="2" style="padding:0.3em;"><small><a href="{}">View on Facebook</a></td></tr></table>'.format(item['url'])
    return item

# http://localhost:8080/content?debug&read&url=https%3A%2F%2Fwww.facebook.com%2FHudsonLibrary.HistoricalSociety%2Fposts%2F10160661375233689
# https://m.facebook.com/HudsonLibrary.HistoricalSociety/posts/10160661375233689
# https://m.facebook.com/shaun.sargent.71/posts/3144719225789531/
# https://www.facebook.com/HudsonCitySchools

