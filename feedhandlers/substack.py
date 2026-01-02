import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)


def resize_image(img_src, width=1272):
    return 'https://substackcdn.com/image/fetch/w_{},c_limit,f_auto,q_auto:good,fl_progressive:steep/'.format(width) + quote_plus(img_src)


def get_content(url, args, site_json, save_debug=False):
    # https://substack.com/api/v1/posts/by-id/96541363
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))

    if split_url.netloc == 'open.substack.com':
        redirect_url = utils.get_redirect_url(url)
        split_url = urlsplit(redirect_url)
        paths = list(filter(None, split_url.path[1:].split('/')))

    if 'post' in paths:
        # https://substack.com/home/post/p-151067817
        m = re.search(r'p-(\d+)', paths[-1])
        if m:
            api_url = '{}://{}/api/v1/posts/by-id/{}'.format(split_url.scheme, split_url.netloc, m.group(1))
    else:
        api_url = '{}://{}/api/v1/posts/{}'.format(split_url.scheme, split_url.netloc, paths[1])
    post_json = utils.get_url_json(api_url)
    if not post_json:
        return None
    if post_json.get('post'):
        return get_post(post_json['post'], args, site_json, save_debug)
    return get_post(post_json, args, site_json, save_debug)


def get_post(post_json, args, site_json, save_debug):
    if save_debug:
        utils.write_file(post_json, './debug/debug.json')

    item = {}
    item['id'] = post_json['id']

    item['url'] = post_json['canonical_url']
    split_url = urlsplit(item['url'])

    item['title'] = post_json['title']

    dt = datetime.fromisoformat(post_json['post_date'].replace('Z', '+00:00'))
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)

    if post_json.get('publishedBylines'):
        item['authors'] = [{"name": x['name']} for x in post_json['publishedBylines']]
        if len(item['authors']) > 0:
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }
    else:
        item['author'] = {
            "name": split_url.netloc
        }
        item['authors'] = []
        item['authors'].append(item['author'])

    if post_json.get('postTags'):
        item['tags'] = []
        for it in post_json['postTags']:
            item['tags'].append(it['name'])

    if post_json.get('cover_image'):
        item['image'] = post_json['cover_image']

    if post_json.get('description'):
        item['summary'] = post_json['description']

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    content_soup = None
    item['content_html'] = ''
    if post_json['audience'] == 'only_paid':
        page_html = utils.get_url_html(item['url'])
        if page_html:
            page_soup = BeautifulSoup(page_html, 'lxml')
            if page_soup.find(class_='paywall-jump'):
                content_soup = page_soup.find(class_='c-content')
        item['content_html'] += '<h2 style="text-align:center;"><a href="{}">This post is for paid subscribers</a></h2>'.format(item['url'])

    if post_json.get('subtitle'):
        item['content_html'] += '<p><em>{}</em></p>'.format(post_json['subtitle'])

    if post_json.get('audio_items'):
        audio = next((it for it in post_json['audio_items'] if it['type'] == 'voiceover'), None)
        if not audio:
            audio = next((it for it in post_json['audio_items'] if it['type'] == 'tts'), None)
        if audio and audio.get('audio_url'):
            item['_audio'] = audio['audio_url']
            attachment = {}
            attachment['url'] = item['_audio']
            attachment['mime_type'] = 'audio/mpeg'
            item['attachments'] = []
            item['attachments'].append(attachment)
            item['content_html'] += utils.add_audio(item['_audio'], '', 'Listen to article', '', '', '', '', '', show_poster=False)

    if post_json['type'] == 'podcast':
        if post_json.get('videoUpload'):
            item['_video'] = utils.get_redirect_url('https://{}/api/v1/video/upload/{}/src?override_publication_id={}&type=hls&preview=false'.format(split_url.netloc, post_json['videoUpload']['id'], post_json['videoUpload']['publication_id']))
            link = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(item['_video']), quote_plus('application/x-mpegURL'), quote_plus(post_json['cover_image']))
            caption = '{}. <a href="{}">Watch</a>'.format(item['title'],link)
            if post_json.get('podcast_url'):
                item['_audio'] = post_json['podcast_url']
                attachment = {}
                attachment['url'] = item['_audio']
                attachment['mime_type'] = 'audio/mpeg'
                item['attachments'] = []
                item['attachments'].append(attachment)
                link = '{}/videojs?src={}&type={}&poster={}'.format(config.server, quote_plus(item['_audio']), quote_plus('audio/mpeg'), quote_plus(post_json['cover_image']))
                caption += ' | <a href="{}">Listen</a>'.format(link)
            caption += ' ({})'.format(utils.calc_duration(post_json['podcast_duration']))
            item['content_html'] += utils.add_video(item['_video'], 'application/x-mpegURL', post_json['cover_image'], caption)
        elif post_json.get('podcastUpload'):
            item['_audio'] = utils.get_redirect_url(post_json['podcast_url'])
            attachment = {}
            attachment['url'] = item['_audio']
            attachment['mime_type'] = 'audio/mpeg'
            item['attachments'] = []
            item['attachments'].append(attachment)
            # TODO: podcast name & url
            item['content_html'] += utils.add_audio(item['_audio'], post_json['cover_image'], item['title'], item['url'], '', '', utils.format_display_date(datetime.fromisoformat(post_json['podcastUpload']['uploaded_at']), date_only=True), post_json['podcastUpload']['duration'])

    if post_json.get('body_html'):
        # utils.write_file(post_json['body_html'], './debug/debug.html')
        soup = BeautifulSoup(post_json['body_html'], 'html.parser')
        if save_debug:
            utils.write_file(str(soup), './debug/debug.html')

        if content_soup:
            paywall = False
            for it in content_soup.find_all(recursive=False):
                if paywall:
                    soup.append(it)
                if it.get('class') and 'paywall-jump' in it['class']:
                    paywall = True

        for el in soup.find_all(class_=['subscription-widget-wrap', 'subscription-widget-wrap-editor', 'paywall-jump']):
            el.decompose()

        for el in soup.find_all(class_=re.compile('button-wrap')):
            if el.name == None:
                continue
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                if re.search(r'comment|email preferences|follow|learn more|schedule|share|subscribe|subscription', data_json['text'], flags=re.I) or re.search(r'subscribe', data_json['url']):
                    el.decompose()

        for el in soup.find_all('h5'):
            el.name = 'h2'

        for el in soup.find_all(class_='digest-post-embed'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                authors = []
                for it in data_json['publishedBylines']:
                    authors.append(it['name'])
                it = el.find_next_sibling()
                if it and it.name == 'blockquote':
                    new_html += '<div>&nbsp;</div><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(data_json['canonical_url'], data_json['title'])
                    new_html += '<div style="font-size:0.9em;">{} &bull; {}</div>'.format(re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)), utils.format_display_date(datetime.fromisoformat(data_json['post_date']), date_only=True))
                    new_html += utils.add_image(data_json['cover_image'])
                    new_html += utils.add_blockquote(it.decode_contents(), False)
                    it.decompose()
                else:
                    new_html += '<div>&nbsp;</div><div style="display:flex; flex-wrap:wrap; gap:1em;">'
                    new_html += '<div style="flex:1; min-width:128px;"><a href="{}"><img src="{}" style="width:100%;" /></a></div>'.format(data_json['canonical_url'], data_json['cover_image'])
                    new_html += '<div style="flex:2; min-width:320px;"><div style="font-size:1.1em; font-weight:bold;"><a href="{}">{}</a></div>'.format(data_json['canonical_url'], data_json['title'])
                    new_html += '<div style="font-size:0.9em;">{} &bull; {}</div>'.format(re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)), utils.format_display_date(datetime.fromisoformat(data_json['post_date']), date_only=True))
                    new_html += '<p><a href="{}" style="text-decoration:none;">Read full story &rarr;</a></p></div></div>'.format(data_json['canonical_url'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled digest-post-embed in ' + item['url'])

        for el in soup.find_all('blockquote'):
            if el.get('style'):
                # likely from above
                continue
            elif not el.get('class'):
                el['style'] = 'border-left:3px solid light-dark(#ccc, #333); margin:1.5em 10px; padding:0.5em 10px;'
                # new_html = utils.add_blockquote(el.decode_contents())
                # new_el = BeautifulSoup(new_html, 'html.parser')
                # el.insert_after(new_el)
                # el.decompose()
            else:
                logger.warning('unhandled blockquote in ' + item['url'])

        for el in soup.find_all(class_='pullquote'):
            # TODO: author/citation?
            new_html = utils.add_pullquote(el.get_text())
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in soup.find_all(class_=['captioned-image-container', 'image-link']):
            if el.name == None or el.name == '':
                continue
            it = el.find('img')
            if not it:
                it = el.find('source')
            if it:
                if it.get('srcset'):
                    img_src = utils.image_from_srcset(it['srcset'], 1000)
                else:
                    img_src = it['src']
                if 'image-link' in el['class']:
                    link = el['href']
                else:
                    it = el.find(class_='image-link')
                    if it:
                        link = it['href']
                    else:
                        link = ''
                it = el.find('figcaption')
                if it:
                    caption = it.decode_contents()
                else:
                    caption = ''
                new_html = utils.add_image(img_src, caption, link=link)
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled captioned-image-container in ' + item['url'])
                print(el)

        for el in soup.find_all(class_='image-gallery-embed'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                if data_json['gallery'].get('caption'):
                    caption = data_json['gallery']['caption']
                else:
                    caption = ''
                gallery_images = []
                new_html += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                for i, it in enumerate(data_json['gallery']['images']):
                    img_src = it['src']
                    thumb = resize_image(it['src'], 848)
                    gallery_images.append({"src": img_src, "caption": caption, "thumb": thumb})
                    new_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, '', link=img_src) + '</div>'
                if i % 2 == 0:
                    new_html += '<div style="flex:1; min-width:360px;">&nbsp;</div>'
                new_html += '</div>'
                if caption:
                    new_html += '<div><small>' + caption + '</small></div><div>&nbsp;</div>'
                gallery_url = '{}/gallery?images={}'.format(config.server, quote_plus(json.dumps(gallery_images)))
                new_html = '<h3><a href="{}" target="_blank">View photo gallery</a></h3>'.format(gallery_url) + new_html
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled image-gallery-embed in ' + item['url'])

        for el in soup.find_all(class_='youtube-wrap'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                new_html = utils.add_embed('https://www.youtube-nocookie.com/embed/{}'.format(data_json['videoId']))
            else:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled youtube-wrap in ' + item['url'])

        for el in soup.find_all(class_='native-video-embed'):
            # https://www.newsguardrealitycheck.com/p/wild-claims-about-la-wildfires-get
            # https://www.mux.com/docs/guides/secure-video-playback
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                video_json = utils.get_url_json('https://' + split_url.netloc + '/api/v1/video/upload/' + data_json['mediaUploadId'])
                if video_json:
                    video_src = 'https://' + split_url.netloc + '/api/v1/video/upload/' + data_json['mediaUploadId'] + '/src'
                    new_html = utils.add_video(video_src, 'video/mp4', video_json['thumbnail_url'], use_videojs=True)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled native-video-embed in ' + item['url'])

        for el in soup.find_all(class_='tweet'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                new_html = utils.add_embed(data_json['url'])
            else:
                it = el.find(class_=['tweet-link-top', 'tweet-link-bottom'])
                if it:
                    new_html = utils.add_embed(it['href'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled tweet in ' + item['url'])

        for el in soup.find_all(class_='bluesky-wrap'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                new_html = utils.add_embed('https://bsky.app/profile/' + data_json['authorDid'] + '/post/' + data_json['postId'])
            elif el.iframe:
                new_html = utils.add_embed(el.iframe['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled bluesky-wrap in ' + item['url'])

        for el in soup.find_all(class_='instagram'):
            new_html = ''
            it = el.find('a', class_='instagram-image')
            if it:
                new_html = utils.add_embed(it['href'])
            elif el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                # TODO: reels?
                new_html = utils.add_embed('https://www.instagram.com/p/' + data_json['instagram_id'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled instagram embed in ' + item['url'])

        for el in soup.find_all('iframe', class_='spotify-wrap'):
            new_html = utils.add_embed(el['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in soup.find_all(class_='apple-podcast-container'):
            new_html = utils.add_embed(el.iframe['src'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in soup.find_all(class_='tiktok-wrap'):
            if el.name == None:
                continue
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                new_html = utils.add_embed(data_json['url'])
            else:
                it = el.find('iframe')
                if it:
                    new_html = utils.add_embed(it['src'])
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled tiktok-wrap in ' + item['url'])

        for el in soup.find_all(class_='datawrapper-wrap'):
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                new_html = utils.add_embed(data_json['url'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.replace_with(new_el)
            else:
                logger.warning('unhandled datawrapper-wrap in ' + item['url'])

        for el in soup.find_all(class_='embedded-post-wrap'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                split_data_url = urlsplit(data_json['url'])
                dt = datetime.fromisoformat(data_json['date'].replace('Z', '+00:00'))
                authors = []
                for it in data_json['bylines']:
                    authors.append(it['name'])
                new_html = '<div style="margin-left:5%; margin-right:5%; padding:8px; border:1px solid black; border-radius:10px;"><div><a href="{}://{}"><img src="{}" style="float:left; width:48px;"/><span style="font-size:1.1em; font-weight:bold;">{}</span></a></div><div style="clear:left;"></div><hr/>'.format(split_data_url.scheme, split_data_url.netloc, data_json['publication_logo_url'], data_json['publication_name'])
                new_html += '<div style="padding:8px;"><h4><a href="{}">{}</a></h4>{}</div><hr/>'.format(data_json['url'], data_json['title'], data_json['truncated_body_text'])
                new_html += '<div style="padding:8px;">{} &bull; {}</div></div>'.format(utils.format_display_date(dt, date_only=True), re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors)))
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

        for el in soup.find_all(class_='embedded-publication-wrap'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                new_html = '<div style="margin-left:5%; margin-right:5%; padding:8px; border:1px solid black; border-radius:10px; text-align:center;"><a href="{}"><img src="{}" style="width:56px;"/><br/><span style="font-size:1.1em; font-weight:bold;">{}</span></a><br/>{}<br/><span style="font-size:0.9em;">By {}</span></div>'.format(data_json['base_url'], data_json['logo_url'], data_json['name'], data_json['hero_text'], data_json['author_name'])
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()

        for el in soup.find_all(class_='poll-embed'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                poll_json = utils.get_url_json('{}://{}/api/v1/poll/{}'.format(split_url.scheme, split_url.netloc, data_json['id']))
                if poll_json:
                    new_html = '<div style="width:80%; margin-right:auto; margin-left:auto; margin-right:auto; border:1px solid black; border-radius:10px; padding:10px;"><h3>{}</h3>'.format(poll_json['question'])
                    for it in poll_json['options']:
                        pct = int(it['votes']/poll_json['total_votes']*100)
                        if pct >= 50:
                            new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to right, lightblue {}%, white {}%);"><p>{}</p><p>{}%</p></div>'.format(pct, 100-pct, it['label'], pct)
                        else:
                            new_html += '<div style="border:1px solid black; border-radius:10px; display:flex; justify-content:space-between; padding-left:8px; padding-right:8px; margin-bottom:8px; background:linear-gradient(to left, white {}%, lightblue {}%);"><p>{}</p><p>{}%</p></div>'.format(100-pct, pct, it['label'], pct)
                    new_html += '<div><small>{} votes &bull; '.format(poll_json['total_votes'])
                    dt = datetime.fromisoformat(poll_json['published_at'].replace('Z', '+00:00'))
                    delta = timedelta(hours=poll_json['expiry'])
                    if dt + delta < datetime.utcnow().replace(tzinfo=timezone.utc):
                        new_html += 'Poll closed'
                    else:
                        new_html += 'Poll open until ' + utils.format_display_date(dt + delta)
                    new_html += '</small></div></div>'
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled poll-embed in ' + item['url'])

        for el in soup.find_all(class_='cashtag-wrap'):
            new_html = ''
            if el.get('data-attrs'):
                data_json = json.loads(el['data-attrs'])
                price_json = utils.get_url_json('{}://{}/api/v1/price/{}'.format(split_url.scheme, split_url.netloc, data_json['symbol']))
                #utils.write_file(price_json, './debug/price.json')
                if price_json:
                    if price_json.get('change_pct'):
                        if price_json['change_pct'] < 0:
                            change = '{:.2f}'.format(price_json['change_pct'])
                            color = 'red'
                            arrow = ' &#8595;'
                        elif price_json['change_pct'] > 0:
                            change = '{:.2f}'.format(price_json['change_pct'])
                            color = 'green'
                            arrow = ' &#8593;'
                        else:
                            change = '0.00'
                            color = 'orange'
                            arrow = ''
                    else:
                        change = '0.00'
                        color = 'orange'
                        arrow = ''
                    new_html = '<a href="https://substack.com/discover/stocks/{0}" style="color:{1};">{0} {2}{3}</a>'.format(data_json['symbol'][1:], color, change, arrow)
            if new_html:
                new_el = BeautifulSoup(new_html, 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled cashtag-wrap in ' + item['url'])

        for el in soup.find_all('a', class_='footnote-anchor'):
            del el['class']
            el.wrap(soup.new_tag('sup'))

        for el in soup.find_all(class_='footnote'):
            it = el.find('a', class_='footnote-number')
            del it['class']
            new_html = '<table><tr><td style="vertical-align:top;">{}</td>'.format(str(it))
            it = el.find(class_='footnote-content')
            note = re.sub(r'^<p>(.*)</p>$', r'\1', it.decode_contents().replace('</p><p>', '<br/><br/>'))
            new_html += '<td style="vertical-align:top;">{}</td></tr></table>'.format(note)
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in soup.find_all('span', class_='mention-wrap'):
            data_json = json.loads(el['data-attrs'])
            new_html = '<a href="https://open.substack.com/users/{}-{}?utm_source=mentions">{}</a>'.format(data_json['id'], data_json['name'].replace(' ', '-'), data_json['name'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in soup.find_all('p', class_='button-wrapper'):
            data_json = json.loads(el['data-attrs'])
            new_html = utils.add_button(data_json['url'], data_json['text'])
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.insert_after(new_el)
            el.decompose()

        for el in soup.find_all(class_=True):
            logger.warning('unhandled class {} in {}'.format(el['class'], item['url']))

        item['content_html'] += str(soup)

    item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    item['content_html'] = re.sub(r'<div><hr/></div>\s*<div><hr/></div>', '<hr/>', item['content_html'])
    item['content_html'] = re.sub(r'<hr/>', '<div>&nbsp;</div><hr/><div>&nbsp;</div>', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    #return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(url)
    api_url = '{}://{}/api/v1/posts?limit=10&offset=0'.format(split_url.scheme, split_url.netloc)
    posts_json = utils.get_url_json(api_url)
    if not posts_json:
        return None
    if save_debug:
        utils.write_file(posts_json, './debug/feed.json')
    n = 0
    items = []
    feed = utils.init_jsonfeed(args)
    for post in posts_json:
        if save_debug:
            logger.debug('getting content from ' + post['canonical_url'])
        item = get_post(post, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                items.append(item)
                n += 1
                if 'max' in args:
                    if n == int(args['max']):
                        break
    feed['items'] = items.copy()
    return feed