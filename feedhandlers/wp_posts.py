import json, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss

import logging

logger = logging.getLogger(__name__)

def render_content(content, url):
    content_html = ''
    for block in content:
        if isinstance(block, str):
            content_html += block

        elif isinstance(block, dict):
            if block.get('tag'):
                if block['tag'] == 'a':
                    content_html += '<a href="{}">{}</a>'.format(block['attributes']['href'], render_content(block['content'], url))
                elif block['tag'] == 'caption':
                    image = next((it for it in block['content'] if it['tag'] == 'img'), None)
                    if image:
                        captions = []
                        caption = next((it for it in block['content'] if isinstance(it, dict) and it['tag'] == 'figcaption'), None)
                        if caption and caption.get('content'):
                            captions.append(render_content(caption['content'], url))
                        caption = next((it for it in block['content'] if isinstance(it, dict) and it['tag'] == 'figcredit'), None)
                        if caption and caption.get('content'):
                            captions.append(render_content(caption['content'], url))
                        content_html += utils.add_image(image['attributes']['src'], ' | '.join(captions))
                    else:
                        logger.warning('unhandled caption tag')
                elif block['tag'] == 'video':
                    if 'time.com' in url and block['attributes'].get('videoid'):
                        content_html += utils.add_embed('https://cdn.jwplayer.com/previews/{}'.format(block['attributes']['videoid']))
                else:
                    print(block['tag'])
                    content_html += '<{0}>{1}</{0}>'.format(block['tag'],render_content(block['content'], url))
            else:
                logger.warning('unhandled dict block without tag')

        else:
            logger.warning('unhandled block type {}'.format(type(block)))

    return content_html


def get_post_content(post, args, save_debug=False):
    if save_debug:
        utils.write_file(post, './debug/debug.json')

    item = {}
    item['id'] = post['guid']['rendered']
    item['url'] = post['link']
    item['title'] = BeautifulSoup('<p>{}</p>'.format(post['title']['rendered']), 'html.parser').get_text()

    dt = datetime.fromisoformat(post['date_gmt']).replace(tzinfo=timezone.utc)
    item['date_published'] = dt.isoformat()
    item['_timestamp'] = dt.timestamp()
    item['_display_date'] = utils.format_display_date(dt)
    dt = datetime.fromisoformat(post['modified_gmt']).replace(tzinfo=timezone.utc)
    item['date_modified'] = dt.isoformat()

    if 'age' in args:
        if not utils.check_age(item, args):
            return None

    authors = []
    item['tags'] = []
    caption = ''
    if post.get('yoast_head_json'):
        for it in post['yoast_head_json']['schema']['@graph']:
            if it['@type'] == 'Person':
                if it.get('name'):
                    authors.append(it['name'])
            elif it['@type'] == 'Article':
                if it.get('keywords'):
                    for tag in it['keywords']:
                        if tag.startswith('category-'):
                            item['tags'] += tag.split('/')[1:]
                        else:
                            item['tags'].append(tag)
            elif it['@type'] == 'ImageObject':
                item['_image'] = it['contentUrl']
                caption = it.get('caption')
    elif post.get('parsely'):
        if post['parsely']['meta'].get('author'):
            for author in post['parsely']['meta']['author']:
                authors.append(author['name'])
        elif post['parsely']['meta'].get('creator'):
            authors = post['parsely']['meta']['creator'].copy()
        if post['parsely']['meta'].get('keywords'):
            item['tags'] = post['parsely']['meta']['keywords'].copy()

    if not authors:
        if post.get('authors'):
            for author in post['authors']:
                authors.append(author['display_name'])
        elif post['_links'].get('author'):
                for link in post['_links']['author']:
                    link_json = utils.get_url_json(link['href'])
                    if link_json:
                        if 'name' in link_json:
                            authors.append(link_json['name'])

    if not item.get('tags'):
        if 'wp:term' in post['_links']:
            for link in post['_links']['wp:term']:
                if link.get('taxonomy') and (link['taxonomy'] == 'category' or link['taxonomy'] == 'post_tag' or link['taxonomy'] == 'ninetofive_guides'):
                    link_json = utils.get_url_json(link['href'])
                    if link_json:
                        for it in link_json:
                            if 'name' in it:
                                item['tags'].append(it['name'])

    if not item.get('_image'):
        if post['_links'].get('wp:featuredmedia'):
            for link in post['_links']['wp:featuredmedia']:
                link_json = utils.get_url_json(link['href'])
                if link_json:
                    if link_json['media_type'] == 'image':
                        item['_image'] = link_json['source_url']
                        captions = []
                        if link_json.get('description'):
                            soup = BeautifulSoup(link_json['description']['rendered'], 'html.parser')
                            caption = soup.get_text().strip()
                            if caption:
                                captions.append(caption)
                        if link_json.get('caption'):
                            soup = BeautifulSoup(link_json['caption']['rendered'], 'html.parser')
                            caption = soup.get_text().strip()
                            if caption:
                                captions.append(caption)
                        caption = ' | '.join(captions)

        if not item.get('_image') and post.get('jetpack_featured_media_url'):
            item['_image'] = post['jetpack_featured_media_url']

        if not item.get('_image') and post.get('acf'):
            if post['acf'].get('hero') and post['acf']['hero'].get('image'):
                item['_image'] = post['acf']['hero']['image']
            elif post['acf'].get('post_hero') and post['acf']['post_hero'].get('image'):
                item['_image'] = post['acf']['post_hero']['image']

    item['author'] = {}
    if authors:
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    else:
        item['author']['name'] = urlsplit(item['url']).netloc

    if not item.get('tags'):
        del item['tags']

    lede = ''
    if item.get('_image'):
        if post.get('content') and post['content'].get('rendered'):
            if post['content']['rendered'].find(item['_image']) == -1:
                lede = utils.add_image(item['_image'], caption)

    # Article summary
    if post.get('excerpt'):
        item['summary'] = BeautifulSoup(post['excerpt']['rendered'], 'html.parser').get_text()
    elif post.get('yoast_head_json'):
        item['summary'] = post['yoast_head_json']['description']

    content_html = ''
    if post.get('subtitle'):
        content_html += '<p><em>{}</em></p>'.format(post['subtitle'])
    elif post.get('meta'):
        if post['meta'].get('sub_heading'):
            content_html += '<p><em>{}</em></p>'.format(post['meta']['sub_heading'])
        elif post['meta'].get('multi_title'):
            multi_title = json.loads(post['meta']['multi_title'])
            if multi_title['titles']['headline'].get('additional') and multi_title['titles']['headline']['additional'].get('headline_subheadline'):
                content_html += '<p><em>{}</em></p>'.format(multi_title['titles']['headline']['additional']['headline_subheadline'])

    if not 'nolead' in args:
        content_html += lede

    if post.get('content') and post['content'].get('structured'):
        logger.debug('getting structured content...')
        item['content_html'] = content_html + render_content(post['content']['structured'], item['url'])
        return item

    elif post.get('content') and post['content'].get('rendered'):
        content_html += post['content']['rendered']

    elif post.get('acf'):
        for module in post['acf']['article_modules']:
            if module['acf_fc_layout'] == 'text_block':
                content_html += module['copy']
            elif module['acf_fc_layout'] == 'list_module':
                content_html += '<h3>{}</h3>'.format(module['title'])
                if module['list_type'] == 'video':
                    if 'youtube' in module['video_url']:
                        for yt in re.findall(r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})', module['video_url']):
                            content_html += utils.add_youtube(yt)
                    else:
                        logger.warning('unhandled video_url in ' + item['url'])
                else:
                    logger.warning('unhandled list_type {} in {}'.format(module['list_type'], item['url']))
                content_html += module['copy']
            elif module['acf_fc_layout'] == 'image_block':
                content_html += utils.add_image(module['image'], module['caption'])
            elif module['acf_fc_layout'] == 'affiliates_block' or module['acf_fc_layout'] == 'inline_recirculation':
                pass
            else:
                logger.warning('unhandled acf_fc_layout module {} in {}'.format(module['acf_fc_layout'], item['url']))

    else:
        logger.warning('unknown post content in {}' + item['url'])

    content_html = content_html.replace('\u2028', '')
    item['content_html'] = format_content(content_html, item)
    return item


def format_content(content_html, item):
    soup = BeautifulSoup(content_html, 'html.parser')

    for el in soup.find_all(id='piano-meter-offer'):
        el.unwrap()

    for el in soup.find_all(id='review-body'):
        # This is probably specific to techhive.com
        review_html = '<br/><div><div style="text-align:center">'
        if el.find('img', src=re.compile(r'Editors-Choice')):
            review_html += '<span style="color:white; background-color:red; padding:0.2em;">EDITOR\'S CHOICE</span><br />'
        it = el.find(class_='starRating')
        if it:
            m = re.search(r'([\d\.]+) out of 5', it['aria-label'])
            if m:
                review_html += '<h1 style="margin:0;">{} / 5</h1>'.format(m.group(1))
        review_html += '</div>'
        it = el.find('p', class_='verdict')
        if it:
            review_html += '<p><em>{}</em></p>'.format(it.get_text())
        it = el.find('ul', class_='pros')
        if it:
            review_html += '<strong>Pros</strong><ul>'
            for li in it.find_all('li'):
                review_html += '<li>{}</li>'.format(li.get_text())
            review_html += '</ul>'
        it = el.find('ul', class_='cons')
        if it:
            review_html += '<strong>Cons</strong><ul>'
            for li in it.find_all('li'):
                review_html += '<li>{}</li>'.format(li.get_text())
            review_html += '</ul>'

        it = soup.find(class_='review-best-price')
        if it:
            for sib in it.next_siblings:
                if sib.name:
                    break
            if sib.get('class') and 'wp-block-price-comparison' in sib['class']:
                review_html += '<strong>Best Prices Today</strong><ul>'
                for record in sib.find_all(class_='price-comparison__record'):
                    if 'price-comparison__record--header' in record['class'] or 'price-comparison__record--footer' in record['class']:
                        continue
                    price = record.find(class_='price-comparison__price').get_text().strip()
                    image = record.find(class_='price-comparison__image')
                    if image.img:
                        vendor = image.img['alt']
                    else:
                        vendor = image.get_text().strip()
                    review_html += '<li>{} from <a href="{}">{}</a></li>'.format(price, utils.get_redirect_url(record.a['href']), vendor)
                review_html += '</ul>'
                sib.decompose()
            it.decompose()

        it = soup.find(class_='review-price')
        if it:
            for sib in it.next_siblings:
                if sib.name:
                    break
            sib.decompose()
            it.decompose()

        review_html += '<hr style="width:80%;"/>'
        new_el = BeautifulSoup(review_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-snopes-fact-check-claim'):
        new_html = '<br/><table style="width:95%; margin-left:auto; margin-right:auto; border-collapse:collapse;">'
        it = el.find(class_='card-header')
        if it:
            new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><h2 style="margin:0;">{}</h2></td></tr>'.format(it.get_text())
        it = el.find(class_='card-body')
        if it:
            new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><span style="font-size:1.2em;">{}</span></td></tr>'.format(it.decode_contents())
        new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='wp-block-snopes-fact-check-rating'):
        new_html = '<br/><table style="width:95%; margin-left:auto; margin-right:auto; border-collapse:collapse;">'
        it = el.find(class_='card-header')
        if it:
            new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><h2 style="margin:0;">{}</h2></td></tr>'.format(it.get_text())
        for body in el.find_all(class_='card-body'):
            img = body.find('img')
            if img:
                rating = body.find(class_=re.compile(r'rating-label'))
                if img and rating:
                    new_html += '<tr><td style="border:1px solid black; padding:0.5em;"><table><tr><td><img src="{}" style="width:120px;"/></td><td style="vertical-align:top;"><h2 style="margin:0;">{}</h2>'.format(img['src'], rating.get_text())
                    link = body.find('a')
                    if link:
                        new_html += '<a href="{}">{}</a></td></tr></table></td></tr>'.format(link['href'], link.get_text())
                    else:
                        new_html += '</td></tr></table></td></tr>'
            else:
                it = body.find(class_='media-body')
                if it.span:
                    it.span.attrs = {}
                    it.span.name = 'h3'
                new_html += '<tr><td style="border:1px solid black; padding:0.5em;">{}</td></tr>'.format(it.decode_contents())
        new_html += '</table>'
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_=['wp-block-gallery', 'wp-block-jetpack-tiled-gallery']):
        for it in el.find_all('img'):
            if it.get('srcset'):
                img_src = utils.image_from_srcset(it['srcset'], 1000)
            else:
                img_src = it['src']
            captions = []
            if it.get('data-image-title'):
                captions.append(it['data-image-title'])
            if it.get('data-image-caption'):
                captions.append(it['data-image-caption'])
            new_el = BeautifulSoup(utils.add_image(img_src, ' | '.join(captions)) + '<br/>', 'html.parser')
            el.insert_before(new_el)
        el.decompose()

    for el in soup.find_all(class_='article-slideshow'):
        for it in el.find_all('li'):
            if it.img.get('srcset'):
                img_src = utils.image_from_srcset(it.img['srcset'], 1000)
            elif it.img.get('data-srcset'):
                img_src = utils.image_from_srcset(it.img['data-srcset'], 1000)
            elif it.img.get('src'):
                img_src = it.img['src']
            elif it.img.get('data-src'):
                img_src = it.img['data-src']
            captions = []
            caption = it.find(class_='slide-caption')
            if caption and caption.get_text().strip():
                captions.append(caption.get_text().strip())
            caption = it.find(class_='slide-credit')
            if caption and caption.get_text().strip():
                captions.append(caption.get_text().strip())
            new_el = BeautifulSoup(utils.add_image(img_src, ' | '.join(captions)) + '<br/>', 'html.parser')
            el.insert_before(new_el)
        el.decompose()

    for el in soup.find_all(class_='post-content-image'):
        img = el.find('img')
        if img:
            if img.get('data-lazy-srcset'):
                img_src = utils.image_from_srcset(img['data-lazy-srcset'], 1000)
            elif img.get('data-lazy-src'):
                img_src = img['data-lazy-src']
            figcaption = el.find('figcaption')
            if figcaption:
                caption = figcaption.get_text()
            else:
                caption = ''
            new_el = BeautifulSoup(utils.add_image(img_src, caption), 'html.parser')
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_='wp-caption'):
        img = el.find('img')
        if not img:
            img = el.find('amp-img')
        if img:
            captions = []
            it = el.find(class_=re.compile(r'caption-text'))
            if it:
                captions.append(it.get_text())
            it = el.find(class_=re.compile(r'image-credit|credits-text'))
            if it:
                captions.append(it.get_text())
            new_el = BeautifulSoup(utils.add_image(img['src'], ' | '.join(captions)), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('wp-caption without img')

    for el in soup.find_all(class_='wp-block-image'):
        img = el.find('img')
        if img:
            if img.get('srcset'):
                img_src = utils.image_from_srcset(img['srcset'], 1000)
            else:
                img_src = img['src']
            captions = []
            if el.figcaption:
                captions.append(el.figcaption.get_text())
            it = el.find(class_='imageCredit')
            if it:
                captions.append(it.get_text())
            if not captions:
                if img.get('data-image-title'):
                    captions.append(img['data-image-title'])
                if img.get('data-image-caption'):
                    captions.append(img['data-image-caption'])
            if el.parent and (el.parent.name == 'p' or el.parent.name == 'div'):
                el_parent = el.parent
            else:
                el_parent = None
            new_el = BeautifulSoup(utils.add_image(img_src, ' | '.join(captions)), 'html.parser')
            if el_parent:
                el_parent.insert_before(new_el)
                if len(el_parent.find_all('img')) > 1:
                    el.decompose()
                else:
                    el_parent.decompose()
                el_parent.decompose()
            else:
                el.insert_after(new_el)
                el.decompose()
        else:
            logger.warning('wp-block-image without img')

    for el in soup.find_all('img', class_=re.compile(r'wp-image-\d+')):
        if el.get('srcset'):
            img_src = utils.image_from_srcset(el['srcset'], 1000)
        else:
            img_src = el['src']
        captions = []
        if el.get('data-image-title'):
            captions.append(el['data-image-title'])
        if el.get('data-image-caption'):
            captions.append(el['data-image-caption'])
        # Check if the img is wrapped in a paragraph. Sometimes more than 1 image can be there
        if el.parent and el.parent.name == 'p':
            el_parent = el.parent
        else:
            el_parent = None
        new_el = BeautifulSoup(utils.add_image(img_src, ' | '.join(captions)), 'html.parser')
        if el_parent:
            el_parent.insert_before(new_el)
            # If there's more than one img, don't decompose the parent yet
            if len(el_parent.find_all('img')) > 1:
                el.decompose()
            else:
                el_parent.decompose()
        else:
            el.insert_after(new_el)
            el.decompose()

    for el in soup.find_all(class_='wp-block-video'):
        video_src = ''
        if el.video:
            video_src = el.video.get('src')
            poster = el.video.get('poster')
            if not video_src:
                if el.video.source:
                    video_src = el.video.source['src']
        if video_src:
            if video_src.endswith('mp4') or video_src.endswith('mov'):
                video_type = 'video/mp4'
            elif video_src.endswith('webm'):
                video_type = 'video/webm'
            elif video_src.endswith('m3u8'):
                video_type = 'application/x-mpegURL'
            else:
                logger.warning('unhandled video type for {} in {}'.format(video_src, item['url']))
                video_type = 'application/x-mpegURL'
            if not poster:
                if video_type == 'video/mp4':
                    poster = '{}/image?url={}&width=1000'.format(config.server, quote_plus(video_src))
                else:
                    poster = '{}/image?width=1000&height=563'.format(config.server)
            if el.figcaption:
                caption = el.figcaption.decode_contents()
            else:
                caption = ''
            new_el = BeautifulSoup(utils.add_video(video_src, video_type, poster, caption), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-video in ' + item['url'])

    for el in soup.find_all(class_='wp-block-audio'):
        audio_src = ''
        if el.audio:
            audio_src = el.audio.get('src')
            if not audio_src:
                if el.audio.source:
                    audio_src = el.audio.source['src']
        if audio_src:
            new_el = BeautifulSoup(utils.add_audio(audio_src), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled wp-block-audio in ' + item['url'])

    for el in soup.find_all('figure', class_='wp-block-embed'):
        new_html = None
        if 'wp-block-embed-youtube' in el['class']:
            new_html = utils.add_embed(el.iframe['src'])
        elif 'wp-block-embed-twitter' in el['class']:
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif 'wp-block-embed-facebook' in el['class']:
            links = el.find_all('a')
            new_html = utils.add_embed(links[-1]['href'])
        elif el.find('video'):
            it = el.find('source')
            if it:
                poster = '{}/image?url={}'.format(config.server, quote_plus(it['src']))
                new_html = utils.add_video(it['src'], it['type'], poster)
        else:
            it = el.find('iframe')
            if it:
                new_html = utils.add_embed(el.iframe['src'])
        if new_html:
            el.insert_after(BeautifulSoup(new_html, 'html.parser'))
            el.decompose()
        else:
            logger.warning('unhandled wp-block-embed in ' + item['url'])

    for el in soup.find_all(class_='embed-youtube'):
        if el.iframe:
            new_el = BeautifulSoup(utils.add_embed(el.iframe['src']), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled embed-youtube in ' + item['url'])

    for el in soup.find_all(class_='video-container'):
        if el.find(class_='js-video'):
            new_el = BeautifulSoup(utils.add_embed('https://cdn.jwplayer.com/previews/{}'.format(it['id'])), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled video-container in ' + item['url'])

    for el in soup.find_all(class_='dtvideos-container'):
        if el.get('data-provider') and el['data-provider'] == 'youtube':
            it = el.find(class_='h-embedded-video')
            if it:
                new_el = BeautifulSoup(utils.add_embed(it['data-url']), 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhanlded youtube dtvideo-container in ' + item['url'])
        else:
            logger.warning('unhandled dtvideos-container in ' + item['url'])

    for el in soup.find_all('iframe'):
        if el.get('src'):
            src = el['src']
        elif el.get('data-src'):
            src = el['data-src']
        else:
            src = ''
        if src:
            new_el = BeautifulSoup(utils.add_embed(src), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unknown iframe src in ' + item['url'])

    for el in soup.find_all(class_='blogstyle__iframe'):
        iframe = el.find('iframe')
        if iframe:
            if iframe.get('src'):
                src = iframe['src']
            elif iframe.get('data-src'):
                src = iframe['data-src']
            else:
                src = ''
            if src:
                new_el = BeautifulSoup(utils.add_embed(src), 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unknown iframe src in ' + item['url'])
        else:
            it = el.find(class_='twitter-tweet')
            if it:
                links = el.find_all('a')
                new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
                el.insert_after(new_el)
                el.decompose()
            else:
                logger.warning('unhandled blogstyle__iframe in ' + item['url'])

    for el in soup.find_all(class_='twitter-tweet'):
        links = el.find_all('a')
        new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(attrs={"data-initial-classes": "twitter-tweet"}):
        links = el.find_all('a')
        new_el = BeautifulSoup(utils.add_embed(links[-1]['href']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='tiktok-embed'):
        new_el = BeautifulSoup(utils.add_embed(el['cite']), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all('blockquote', class_='wp-block-quote'):
        it = el.find('cite')
        if it:
            author = it.get_text()
            it.decompose()
            new_el = BeautifulSoup(utils.add_pullquote(el.decode_contents(), author), 'html.parser')
        else:
            new_el = BeautifulSoup(utils.add_blockquote(el.decode_contents()), 'html.parser')
        el.insert_after(new_el)
        el.decompose()

    for el in soup.find_all(class_='article-pull-quote'):
        quote = el.find(class_='text')
        if quote:
            it = el.find(class_='author')
            if it:
                author = it.get_text()
            else:
                author = ''
            new_el = BeautifulSoup(utils.add_pullquote(quote.decode_contents(), author), 'html.parser')
            el.insert_after(new_el)
            el.decompose()
        else:
            logger.warning('unhandled article-pull-quote')

    for el in soup.find_all(class_='bottom-line-module'):
        it = el.find(class_='module-title')
        if it:
            it.name = 'h4'
            it.attrs = {}
        el.name = 'blockquote'
        el.attrs = {}
        el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.find_all('a', href=re.compile(r'go\.redirectingat\.com/')):
        el['href'] = utils.get_redirect_url(el['href'])

    for el in soup.find_all(class_='product-link'):
        href = utils.get_redirect_url(el['href'])
        el.attrs = {}
        el['href'] = href

    for el in soup.find_all(class_='wp-block-product-widget-block'):
        if el.find(id='mentioned-in-this-article'):
            el.decompose()

    for el in soup.find_all(class_=re.compile(r'wp-block-bigbite-multi-title|wp-block-product-widget-block')):
        el.decompose()

    for el in soup.find_all(id=re.compile(r'^ad_|\bad\b')):
        el.decompose()

    for el in soup.find_all(class_=re.compile(r'^ad_|\bad\b')):
        el.decompose()

    for el in soup.find_all(['aside', 'ins', 'script', 'style']):
        el.decompose()

    return str(soup)

def get_content(url, args, save_debug=False):
    split_url = urlsplit(url)
    paths = list(filter(None, split_url.path[1:].split('/')))
    slug = paths[-1].split('.')[0]
    post_url = '{}://{}/wp-json/wp/v2/posts?slug={}'.format(split_url.scheme, split_url.netloc, slug)
    post = utils.get_url_json(post_url)
    if post:
        return get_post_content(post[0], args, save_debug)

    url_root = '{}://{}'.format(split_url.scheme, split_url.netloc)
    article_html = utils.get_url_html(url)
    if article_html:
        if save_debug:
            utils.write_file(article_html, './debug/debug.html')
        post_url = ''
        soup = BeautifulSoup(article_html, 'html.parser')
        for link in soup.find_all('link', attrs={"type":"application/json"}):
            print(link['href'])
            if re.search(r'/wp-json/wp/v2/', link['href']):
                post_url = link['href']
                break
        if not post_url:
            # Search for the post id and assume the wp-json path
            m = re.search(r'{}://{}/\?p=(\d+)'.format(split_url.scheme, split_url.netloc), article_html)
            if m:
                post_url = m.group(0)
            else:
                m = re.search(r'data-content_cms_id="(\d+)"', article_html)
                if m:
                    post_url = '{}://{}/wp-json/wp/v2/posts/{}'.format(split_url.scheme, split_url.netloc, m.group(1))
                else:
                    logger.warning('unable to find wp-json post url in ' + url)
                    return None
    post = utils.get_url_json(post_url)
    if post:
        return get_post_content(post, args, save_debug)
    return None


def get_feed(args, save_debug=False):
    if '/wp-json/' in args['url']:
        n = 0
        feed = utils.init_jsonfeed(args)
        posts = utils.get_url_json(args['url'])
        if posts:
            for post in posts:
                if save_debug:
                    logger.debug('getting content from ' + post['link'])
                item = get_post_content(post, args, save_debug)
                if item:
                    if utils.filter_item(item, args) == True:
                        feed['items'].append(item)
                        n += 1
                        if 'max' in args:
                            if n == int(args['max']):
                                break
    else:
        feed = rss.get_feed(args, save_debug, get_content)
    return feed

def test_handler():
    feeds = ['https://www.techhive.com/wp-json/wp/v2/posts?story_types=3'
             'https://www.9to5mac.com/guides/review/feed',
             'https://www.9to5google.com/feature/review/feed']
    for url in feeds:
        get_feed({"url": url}, True)
