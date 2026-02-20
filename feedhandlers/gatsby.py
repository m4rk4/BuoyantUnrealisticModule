import json, markdown2, pytz, re
import dateutil.parser
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils
from feedhandlers import rss, semafor

import logging

logger = logging.getLogger(__name__)


def resize_image(img_path, site_json, width=1080):
    return  '{}{}?w={}'.format(site_json['image_url'], img_path, width)


def add_image(image, site_json, width=1080):
    captions = []
    if image['entity'].get('caption'):
        captions.append(re.sub(r'</?p>', '', image['entity']['caption']))
    if image['entity'].get('credit'):
        captions.append(image['entity']['credit'])
    img_src = resize_image(image['entity']['mediaImage']['url'], site_json, width)
    return utils.add_image(img_src, ' | '.join(captions))


def render_content(content, site_json):
    content_html = ''
    if content['entity']['type'] == 'ParagraphContent':
        content_html += content['entity']['content']['value']

    elif content['entity']['type'] == 'ParagraphImageToolkitElement':
        content_html += add_image(content['entity']['image'], site_json)

    elif content['entity']['type'] == 'ParagraphImageGroup':
        for image in content['entity']['images']:
            content_html += add_image(image, site_json)

    elif content['entity']['type'] == 'ParagraphGalleryInlineElement':
        content_html += '<h3>Gallery: {}</h3>'.format(content['entity']['photoGallery']['entity']['title'])
        for image in content['entity']['photoGallery']['entity']['images']:
            content_html += add_image(image, site_json)

    elif content['entity']['type'] == 'ParagraphImmersiveLead':
        if content['entity'].get('immersiveImage'):
            content_html += add_image(content['entity']['immersiveImage'], site_json)
        else:
            logger.warning('unhandled ParagraphImmersiveLead')

    elif content['entity']['type'] == 'ParagraphVideoToolkit':
        if content['entity']['video']['entity'].get('image'):
            poster = resize_image(content['entity']['video']['entity']['image']['entity']['mediaImage']['url'], site_json)
        else:
            poster = ''
        caption = '<a href="https://www.nationalgeographic.co.uk{}"><strong>{}</strong></a>'.format(content['entity']['video']['entity']['url']['path'], content['entity']['video']['entity']['title'])
        if content['entity']['video']['entity'].get('promoSummary'):
            caption += '<br/>{}'.format(re.sub(r'</?p>', '', content['entity']['video']['entity']['promoSummary']['value']))
        video_src = ''
        if content['entity']['video']['entity']['video']['entity'].get('smilUrl'):
            smil = utils.get_url_html(content['entity']['video']['entity']['video']['entity']['smilUrl'])
            soup = BeautifulSoup(smil, 'html.parser')
            video_src = soup.video['src']
            video_type = soup.video['type']
        if video_src:
            content_html += utils.add_video(video_src, video_type, poster, caption)
        else:
            logger.warning('unhandled ParagraphVideoToolkit')

    elif content['entity']['type'] == 'ParagraphPullQuote':
        content_html += utils.add_pullquote(content['entity']['pullQuote'], content['entity']['source'])

    elif content['entity']['type'] == 'ParagraphInlinePromos':
        pass

    else:
        logger.warning('unhandled content type ' + content['entity']['type'])

    return content_html


def get_content(url, args, site_json, save_debug=False):
    split_url = urlsplit(url)
    if site_json.get('page_data_prefix') and split_url.path.startswith(site_json['page_data_prefix']):
        path = split_url.path[len(site_json['page_data_prefix']):]
    else:
        path = split_url.path
    if path.endswith('/'):
        path = path[:-1]
    api_url = split_url.scheme + '://' + split_url.netloc + site_json['page_data_prefix'] + '/page-data' + path + '/page-data.json'
    # api_url = '{}://{}{}/page-data{}/page-data.json'.format(split_url.scheme, split_url.netloc, site_json['page_data_prefix'], path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None
    if save_debug:
        utils.write_file(api_json, './debug/debug.json')

    # article_json = api_json['result']['pageContext']['node']['data']['content']
    # if save_debug:
    #     utils.write_file(article_json, './debug/debug.json')

    site_metadata = None
    if api_json.get('staticQueryHashes'):
        for it in api_json['staticQueryHashes']:
            sq_url = '{}://{}/page-data/sq/d/{}.json'.format(split_url.scheme, split_url.netloc, it)
            sq_json = utils.get_url_json(sq_url)
            if sq_json:
                if sq_json.get('data') and sq_json['data'].get('site') and sq_json['data']['site'].get('siteMetadata'):
                    site_metadata = sq_json['data']['site']['siteMetadata']
                    break

    page_context = api_json['result']['pageContext']
    item = {}
    if page_context.get('id'):
        item['id'] = page_context['id']
    else:
        item['id'] = api_json['path']

    item['url'] = 'https://' + split_url.netloc + api_json['path']

    if api_json['result'].get('data') and api_json['result']['data'].get('markdownRemark'):
        md_remark = api_json['result']['data']['markdownRemark']
        item['title'] = md_remark['frontmatter']['title']

        if md_remark['frontmatter'].get('rawDate'):
            dt = datetime.fromisoformat(md_remark['frontmatter']['rawDate'])
        elif md_remark['frontmatter'].get('date'):
            dt = dateutil.parser.parse(md_remark['frontmatter']['date'])
        else:
            dt = None
        if dt:
            if not dt.tzinfo:
                tz_loc = pytz.timezone(config.local_tz)
                dt = tz_loc.localize(dt).astimezone(pytz.utc)
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = utils.format_display_date(dt)

        if md_remark['frontmatter'].get('rawUpdatedAt'):
            dt = datetime.fromisoformat(md_remark['frontmatter']['rawUpdatedAt'])
            item['date_modified'] = dt.isoformat()

        if site_metadata:
            if site_metadata.get('author'):
                item['author'] = {"name": site_metadata['author']}
            elif site_metadata.get('title'):
                item['author'] = {"name": site_metadata['title']}

        if md_remark['frontmatter'].get('image'):
            item['_image'] = md_remark['frontmatter']['image']['childImageSharp']['fluid']['src']
            if item['_image'].startswith('/'):
                item['_image'] = 'https://' + split_url.netloc + item['_image']

        if md_remark['frontmatter'].get('description'):
            item['summary'] = md_remark['frontmatter']['description']
        elif md_remark.get('excerpt'):
            item['summary'] = md_remark['excerpt']

        if md_remark.get('html'):
            soup = BeautifulSoup(md_remark['html'], 'html.parser')
            for el in soup.find_all(class_='gatsby-resp-image-wrapper'):
                it = el.find('a', class_='gatsby-resp-image-link')
                if it:
                    img_src = it['href']
                else:
                    it = el.find('img')
                    if it:
                        if it.get('srcset'):
                            img_src = utils.image_from_srcset(it['srcset'], 1200)
                        else:
                            img_src = it['src']
                if img_src.startswith('/'):
                    img_src = 'https://' + split_url.netloc + img_src
                # TODO: captions
                new_el = BeautifulSoup(utils.add_image(img_src), 'html.parser')
                if el.parent and el.parent.name == 'p':
                    el.parent.replace_with(new_el)
                else:
                    el.replace_with(new_el)

            for el in soup.find_all('iframe'):
                new_el = BeautifulSoup(utils.add_embed(el['src']), 'html.parser')
                if el.parent and el.parent.name == 'p':
                    el.parent.replace_with(new_el)
                else:
                    el.replace_with(new_el)

            for el in soup.find_all('a', class_='anchor'):
                it = el.find('svg')
                if it:
                    it.decompose()
                el.unwrap()

            item['content_html'] = str(soup)

        # if article_json.get('subHeadline'):
        #     item['summary'] = article_json['subHeadline']
        #     item['content_html'] += '<p><em>{}</em></p>'.format(article_json['subHeadline'])
        #
        # if article_json.get('immersiveLead'):
        #     item['content_html'] += render_content(article_json['immersiveLead'], site_json)
        # elif article_json.get('image'):
        #     item['content_html'] += add_image(article_json['image'], site_json)
        #
        # if article_json.get('mainContent'):
        #     for content in article_json['mainContent']:
        #         item['content_html'] += render_content(content, site_json)
        #
        # if article_json.get('images'):
        #     for content in article_json['images']:
        #         item['content_html'] += add_image(content, site_json)

    elif api_json['result'].get('data') and api_json['result']['data'].get('wpPost'):
        # https://www.gatsbyjs.com/blog/
        wp_post = api_json['result']['data']['wpPost']
        item['title'] = wp_post['title']

        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = dateutil.parser.parse(wp_post['date'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        if wp_post.get('author') and wp_post['author'].get('node'):
            item['author'] = {"name": wp_post['author']['node']['name']}

        if wp_post.get('tags') and wp_post['tags'].get('nodes'):
            item['tags'] = []
            for it in wp_post['tags']['nodes']:
                item['tags'].append(it['name'])

        if wp_post.get('rawExcerpt') and wp_post['rawExcerpt'].get('text'):
            item['summary'] = wp_post['rawExcerpt']['text']

        if wp_post.get('flexibleContent') and wp_post['flexibleContent'].get('blocks'):
            item['content_html'] = ''
            for block in wp_post['flexibleContent']['blocks']:
                if block['__typename'] == 'WpPost_Flexiblecontent_Blocks_RichText':
                    item['content_html'] += block['richText']
                elif block['__typename'] == 'WpPost_Flexiblecontent_Blocks_Image':
                    if block['image']['gatsbyImage']['images']['fallback'].get('srcSet'):
                        img_src = utils.image_from_srcset(block['image']['gatsbyImage']['images']['fallback']['srcSet'], 1200)
                    else:
                        img_src = block['image']['gatsbyImage']['images']['fallback']['src']
                    if img_src.startswith('/'):
                        img_src = 'https://' + split_url.netloc + img_src
                    # TODO: captions
                    item['content_html'] += utils.add_image(img_src)
                elif block['__typename'] == 'WpPost_Flexiblecontent_Blocks_Embed':
                    item['content_html'] += utils.add_embed(block['embedUrl'])
                elif block['__typename'] == 'WpPost_Flexiblecontent_Blocks_CodeBlock':
                    if block.get('filename'):
                        item['content_html'] += '<div style="font-weight:bold; background-color:#aaa;">&nbsp;' + block['filename'] + '</div>'
                    item['content_html'] += '<pre style="margin-top:0; padding:0.5em; white-space:pre; overflow-x:auto; background:#F2F2F2;"><code>' + block['code'].replace('<', '&lt;').replace('>', '&gt;') + '</code></pre>'
                elif block['__typename'] == 'WpPost_Flexiblecontent_Blocks_Pullquote':
                    item['content_html'] += utils.add_pullquote(block['pullquoteText'], block.get('citation'))
                else:
                    logger.warning('unhandled flexibleContent block type {} in {}'.format(block['__typename'], item['url']))

    elif api_json['result'].get('data') and api_json['result']['data'].get('story'):
        # https://www.rockefellercenter.com/magazine/
        story_data = api_json['result']['data']['story']
        item['title'] = story_data['titleAndSlug']['title']

        dt = datetime.fromisoformat(story_data['publishAt'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        if story_data.get('authors'):
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(story_data['authors']))

        if story_data.get('poster'):
            item['_image'] = story_data['poster']['asset']['fluid']['src']

        if story_data.get('excerpt'):
            item['summary'] = story_data['excerpt']

        if story_data.get('_rawBody'):
            item['content_html'] = ''
            for block in story_data['_rawBody']:
                item['content_html'] += semafor.render_block(block)
            item['content_html'] = item['content_html'].replace('https://img.semafor.com', site_json['image_path'])

    elif api_json['result'].get('data') and api_json['result']['data'].get('post'):
        # https://thefactbase.com/
        post_json = api_json['result']['data']['post']
        item['title'] = post_json['title']

        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = dateutil.parser.parse(post_json['date'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        if post_json.get('author'):
            item['author'] = {"name": post_json['author']['name']}

        item['tags'] = []
        if post_json.get('keywords'):
            item['tags'] += post_json['keywords'].copy()
        if post_json.get('tags'):
            for it in post_json['tags']:
                item['tags'].append(it['name'])

        if post_json.get('excerpt'):
            item['summary'] = post_json['excerpt']

        if post_json.get('thumbnail'):
            if post_json['thumbnail'].get('ImageSharp_hero'):
                item['_image'] = 'https://' + split_url.netloc + post_json['thumbnail']['ImageSharp_hero']['images']['fallback']['src']
            elif post_json['thumbnail'].get('ImageSharp_vertical'):
                item['_image'] = 'https://' + split_url.netloc + post_json['thumbnail']['ImageSharp_vertical']['images']['fallback']['src']

        item['content_html'] = ''
        if '_image' in item:
            item['content_html'] += utils.add_image(item['_image'])

        # for mdx in re.findall(r'mdx\((\".*?)\)(?=, mdx\(\"|\);\n}\n;)', post_json['body'], flags=re.S):
        #     item['content_html'] += render_mdx(mdx, 'https://' + split_url.netloc)
        item['content_html'] += render_mdx_layout(post_json['body'], split_url.netloc, save_debug)

    elif api_json['result'].get('data') and api_json['result']['data'].get('mdx'):
        # https://ericmigi.com/blog/introducing-two-new-pebbleos-watches
        # https://ente.io/blog/r/gpt-is-my-friend/
        item['id'] = page_context['id']
        item['url'] = url
        item['title'] = api_json['result']['data']['mdx']['frontmatter']['title']

        tz_loc = pytz.timezone(config.local_tz)
        dt_loc = dateutil.parser.parse(api_json['result']['data']['mdx']['frontmatter']['date'])
        dt = tz_loc.localize(dt_loc).astimezone(pytz.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        m = re.search(r'"lastEditedTime":\s*"([^"]+)', api_json['result']['data']['mdx']['body'])
        if m:
            dt = datetime.fromisoformat(m.group(1))
            item['date_modified'] = dt.isoformat()

        if api_json['result']['data']['mdx']['frontmatter'].get('author'):
            item['author'] = {
                "name": api_json['result']['data']['mdx']['frontmatter']['author']
            }
        else:
            item['author'] = {
                "name": split_url.netloc
            }
        item['authors'] = []
        item['authors'].append(item['author'])

        if api_json['result']['data']['mdx']['frontmatter'].get('socialImage'):
            item['_image'] = 'https://' + split_url.netloc + api_json['result']['data']['mdx']['frontmatter']['socialImage']

        if api_json['result']['data']['mdx']['frontmatter'].get('subtitle'):
            item['summery'] = api_json['result']['data']['mdx']['frontmatter']['subtitle']

        item['content_html'] = render_mdx_layout(api_json['result']['data']['mdx']['body'], split_url.netloc, save_debug)

    elif api_json['result'].get('data') and api_json['result']['data'].get('essay'):
        # https://publicdomainreview.org/essays/
        essay_data = api_json['result']['data']['essay']['data']
        item['title'] = essay_data['Title']

        dt = datetime.fromisoformat(essay_data['Published_Date'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

        if essay_data.get('Contributors'):
            authors = []
            for it in essay_data['Contributors']:
                authors.append(it['data']['Name'])
            item['author'] = {}
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))

        item['tags'] = []
        if essay_data.get('Categories'):
            item['tags'] += essay_data['Categories'].copy()
        if essay_data.get('Tags'):
            for it in essay_data['Tags']:
                item['tags'].append(it['data']['Label'])
        if not item.get('tags'):
            del item['tags']

        if essay_data.get('Featured_Image_Path'):
            item['_image'] = site_json['image_path'] + essay_data['Featured_Image_Path']

        item['content_html'] = ''
        if essay_data.get('Intro'):
            item['summary'] = essay_data['Intro']
            item['content_html'] += markdown2.markdown(essay_data['Intro'])

        body = markdown2.markdown(essay_data['Body'])
        def sub_image(matchobj):
            nonlocal site_json
            m = re.search(r'path=\{([^\}]+)\}', matchobj.group(0))
            if m:
                if m.group(1).startswith('/'):
                    img_src = site_json['image_path'] + m.group(1)
                else:
                    img_src = m.group(1)
            m = re.search(r'caption=\{([^\}]+)\}', matchobj.group(0))
            if m:
                caption = m.group(1)
            else:
                caption = ''
            return utils.add_image(img_src, caption)
        body = re.sub(r'<p>\{image.*?endimage\}</p>', sub_image, body, flags=re.S)

        soup = BeautifulSoup(body, 'html.parser')
        for el in soup.find_all('blockquote'):
            el.attrs = {}
            el['style'] = 'border-left:3px solid #ccc; margin:1.5em 10px; padding:0.5em 10px;'
        item['content_html'] += str(soup)

        if essay_data.get('Footnotes'):
            item['content_html'] = re.sub(r'\[\^(\d+)\]', r'<sup>\1</sup>', item['content_html'])
            item['content_html'] += '<div>&nbsp;</div><hr/><h3>Notes:</h3>'
            item['content_html'] += '<ol>' + re.sub(r'\[\^\d+\]:(.*?)(\n|$)', r'<li>\1</li>', essay_data['Footnotes']) + '</ol>'

    elif page_context.get('blocks'):
        # https://istories.media/en/stories/2025/06/10/telegram-fsb/
        item['title'] = page_context['header']
        dt = datetime.fromisoformat(page_context['initially_published_at'])
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)
        item['authors'] = [{"name": x['first_name_en'] + ' ' + x['last_name_en']} for x in page_context['authors_list']]
        if len(item['authors']) > 0:
            item['author'] = {
                "name": re.sub(r'(,)([^,]+)$', r' and\2', ', '.join([x['name'] for x in item['authors']]))
            }
        if page_context['meta'].get('og_description'):
            item['summary'] = page_context['meta']['og_description']
        if page_context['meta'].get('og_image'):
            item['image'] = page_context['meta']['og_image']
        item['content_html'] = ''
        if page_context.get('lead'):
            if 'summary' not in item:
                item['summary'] = page_context['lead']
            item['content_html'] += '<p><em>' + page_context['lead'] + '</em></p>'
        if page_context.get('entry_image'):
            if 'image' not in item:
                item['image'] = page_context['entry_image'][0]['url_1x']
            item['content_html'] += utils.add_image(page_context['entry_image'][0]['url_1x'], page_context.get('entry_image_credit'))
        for block in page_context['blocks']:
            if block['type'] in ['p', 'h2', 'ul']:
                item['content_html'] += '<{0}>{1}</{0}>'.format(block['type'], block['data'])
            elif block['type'] == 'image-embed' or block['type'] == 'two-images-embed':
                gallery_images = []
                for image in block['data']['data']['images']:
                    captions = []
                    if image.get('caption'):
                        captions.append(image['caption'])
                    if image.get('credit'):
                        captions.append(image['credit'])
                    img_src = image['imagesList'][0]['url_1x']
                    thumb = image['imagesList'][-1]['url_1x']
                    gallery_images.append({"src": img_src, "caption": ' | '.join(captions), "thumb": thumb})
                if len(gallery_images) == 1:
                    item['content_html'] += utils.add_image(gallery_images[0]['src'], gallery_images[0]['caption'])
                else:
                    gallery_url = config.server + '/gallery?images=' + quote_plus(json.dumps(gallery_images))
                    item['content_html'] += '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                    for image in gallery_images:
                        item['content_html'] += '<div style="flex:1; min-width:360px;">' + utils.add_image(image['thumb'], image['caption'], link=gallery_url) + '</div>'
                    item['content_html'] += '</div>'
            elif block['type'] == 'images-with-text-embed':
                gallery_images = []
                gallery_html = '<div style="display:flex; flex-wrap:wrap; gap:16px 8px;">'
                for i, image in enumerate(block['data']['data']['items']):
                    img_src = image['image'][0]['url_1x']
                    thumb = image['image'][-1]['url_1x']
                    desc = ''
                    if image.get('creditBlock'):
                        desc += image['creditBlock']
                    if image.get('textBlock'):
                        desc += image['textBlock']
                    gallery_images.append({"src": img_src, "caption": '', "thumb": thumb, "desc": desc})
                    gallery_html += '<div style="flex:1; min-width:360px;">' + utils.add_image(thumb, '', link=img_src, desc=desc) + '</div>'
                if i % 2 == 0:
                    gallery_html += '<div style="flex:1; min-width:360px;">&nbsp;</div>'
                gallery_html += '</div>'
                gallery_url = config.server + '/gallery?images=' + quote_plus(json.dumps(gallery_images))
                if block['data']['data'].get('header'):
                    item['content_html'] += '<h3>{} (<a href="{}" target="_blank">view gallery</a>)</h3>'.format(block['data']['data']['header'], gallery_url)
                item['content_html'] += gallery_html
            elif block['type'] == 'video-embed':
                if block['data']['data']['provider'] == 'youtube':
                    item['content_html'] += utils.add_embed(block['data']['data']['url'])
                elif block['data']['data']['provider'] == 'viqeo':
                    page_html = utils.get_url_html(block['data']['data']['url'])
                    if page_html:
                        soup = BeautifulSoup(page_html, 'lxml')
                        el = soup.find('script', attrs={"type": "text/javascript"}, string=re.compile(r'^window\.DATA ='))
                        if el:
                            i = el.string.find('{')
                            j = el.string.rfind('}') + 1
                            data_json = json.loads(el.string[i:j])
                            video = utils.closest_dict(data_json['metadata']['mediaFiles'], 'bitrate', 1500000)
                            file = next((it for it in data_json['metadata']['mediaFiles'] if it['type'] == 'image/jpeg'), None)
                            if file:
                                poster = file['url']
                            else:
                                poster = ''
                            item['content_html'] += utils.add_video(video['url'], video['type'], poster, data_json['metadata']['type'], use_videojs=True)
                else:
                    logger.warning('unhandled video-embed provider {} in {}'.format(block['data']['data']['provider'], item['url']))
            elif block['type'] == 'gif-embed':
                captions = []
                if block['data']['data'].get('caption'):
                    captions.append(block['data']['data']['caption'])
                if block['data']['data'].get('author'):
                    captions.append(block['data']['data']['author'])
                item['content_html'] += utils.add_video(block['data']['data']['videosList'][0]['url'], block['data']['data']['videosList'][0]['content_type'], '', ' | '.join(captions), use_videojs=True)
            elif block['type'] == 'telegram-embed':
                item['content_html'] += utils.add_embed(block['data']['data']['url'])
            elif block['type'] == 'visualization-embed':
                if block['data']['data']['url'].startswith('https://static.istories.media/iframes/'):
                    item['content_html'] += utils.add_image(config.server + '/screenshot?url=' + quote_plus(block['data']['data']['url']), link=block['data']['data']['url'])
                else:
                    logger.warning('unhandled visualization-embed ' + block['data']['data']['url'])
            elif block['type'] == 'google-maps-embed':
                if block['data']['data']['url'].startswith('https://snazzymaps.com/embed/'):
                    item['content_html'] += utils.add_image(config.server + '/screenshot?url=' + quote_plus(block['data']['data']['url']), link=block['data']['data']['url'])
                else:
                    logger.warning('unhandled google-maps-embed ' + block['data']['data']['url'])
            elif block['type'] == 'quotation-embed':
                item['content_html'] += utils.add_pullquote(block['data']['data']['header'], block['data']['data'].get('author'))
            elif block['type'] == 'table-embed':
                item['content_html'] += '<table style="margin:auto; border-collapse:collapse; border-top:1px solid light-dark(#333,#ccc);">'
                for i, row in enumerate(block['data']['data']['content']):
                    item['content_html'] += '<tr>'
                    for td in row:
                        if i == 0:
                            item['content_html'] += '<th style="padding:4px; border-bottom:1px solid light-dark(#333,#ccc);">' + td + '</th>'
                        else:
                            item['content_html'] += '<td style="padding:4px; border-bottom:1px solid light-dark(#333,#ccc);">' + td + '</td>'
                    item['content_html'] += '</tr>'
                item['content_html'] += '</table>'
            elif block['type'] == 'text-with-number-embed':
                item['content_html'] += '<div style="width:100%; min-width:320px; max-width:540px; margin-left:auto; margin-right:auto; padding:0 0.5em 0 0.5em; border:1px solid light-dark(#333, #ccc); border-radius:10px; background-color:#aaa;">'
                item['content_html'] += '<div style="font-size:3em; font-weight:bold;">' + block['data']['data']['number'] + '</div>'
                if block['data']['data'].get('header'):
                    item['content_html'] += '<div style="font-weight:bold;">' + block['data']['data']['header'] + '</div>'
                item['content_html'] += '<p>' + block['data']['data']['text'] + '</p>'
                item['content_html'] += '</div>'
            elif block['type'] == 'drop-down-embed':
                item['content_html'] += '<details style="padding:0.5em; border:1px solid light-dark(#333,#ccc); border-radius:10px; background-color:#aaa;"><summary><span style="font-size:1.1em; font-weight:bold;">' + block['data']['data']['header'] + '</span></summary>' + block['data']['data']['block'] + '</details>'
            elif block['type'] == 'custom-code-embed' and block['data']['data']['code'].startswith('<iframe'):
                m = re.search(r'src="([^"]+)', block['data']['data']['code'])
                if m:
                    item['content_html'] += utils.add_embed(m.group(1))
            elif block['type'] == 'donate-embed' or block['type'] == 'donation-form-embed':
                continue
            else:
                logger.warning('unhandled block type {} in {}'.format(block['type'], item['url']))

    if page_context.get('category'):
        if not item.get('tags'):
            item['tags'] = []
        if page_context['category'] not in item['tags']:
            item['tags'].append(page_context['category'])

    if item.get('content_html'):
        item['content_html'] = re.sub(r'</(figure|table)>\s*<(figure|table)', r'</\1><div>&nbsp;</div><\2', item['content_html'])
    return item


def get_feed(url, args, site_json, save_debug=False):
    if url.endswith('.xml'):
        return rss.get_feed(url, args, site_json, save_debug, get_content)

    split_url = urlsplit(args['url'])
    if len(split_url.path) <= 1:
        path = '/index'
    elif site_json.get('page_data_prefix') and split_url.path.startswith(site_json['page_data_prefix']):
        path = split_url.path[len(site_json['page_data_prefix']):]
    else:
        path = split_url.path
    if path.endswith('/'):
        path = path[:-1]
    api_url = '{}://{}{}/page-data{}/page-data.json'.format(split_url.scheme, split_url.netloc, site_json['page_data_prefix'], path)
    api_json = utils.get_url_json(api_url)
    if not api_json:
        return None

    page_json = api_json['result']['pageContext']['node']['data']['content']
    if save_debug:
        utils.write_file(page_json, './debug/feed.json')

    articles = []
    for content in page_json['mainContent']:
        if content['entity']['type'] == 'ParagraphContentPackage1':
            articles.append(content['entity']['cardGlobalLarge']['entity']['url']['path'])
        else:
            logger.warning('unhandled feed content type ' + content['entity']['type'])

    for content in page_json['termContent']['data']['featured']:
        articles.append(content['props']['data']['url'])

    for content in page_json['termContent']['data']['pagination']:
        for it in content:
            articles.append(it[1])

    feed = utils.init_jsonfeed(args)
    feed['title'] = page_json['title']
    feed_items = []
    for path in articles:
        url = '{}://{}{}'.format(split_url.scheme, split_url.netloc, path)
        if save_debug:
            logger.debug('getting content for ' + url)
        item = get_content(url, args, site_json, save_debug)
        if item:
            if utils.filter_item(item, args) == True:
                feed_items.append(item)

    feed['items'] = sorted(feed_items, key=lambda i: i['_timestamp'], reverse=True)
    return feed


def parse_mdx_str(mdx_str):
    # tag
    m = re.search(r'mdx\("([^"]+)",\s+', mdx_str)
    if not m:
        return None
    tag = m.group(1)
    n = len(m.group(0))

    # null or {params}
    if mdx_str[n:].startswith('null'):
        params = None
        n += 4
    elif mdx_str[n] == '{':
        m = re.search(r'{\s*', mdx_str[n:])
        n += len(m.group(0))
        params = {}
        while True:
            m = re.search(r'"?([^:\"]+)"?:\s+', mdx_str[n:])
            if m:
                key = m.group(1)
                n += len(m.group(0))
                if mdx_str[n] == '{':
                    params[key] = {}
                    m = re.search(r'{\s*', mdx_str[n:])
                    n += len(m.group(0))
                    while True:
                        m = re.search(r'"([^"]+)":\s?"([^"]+)"', mdx_str[n:])
                        if m:
                            k = m.group(1)
                            v = m.group(2)
                            params[key][k] = v
                            # print(m.group(0))
                            n += len(m.group(0))
                            m = re.search(r',?\s*', mdx_str[n:])
                            if m:
                                n += len(m.group(0))
                            if mdx_str[n] == '}':
                                m = re.search(r'}\s+', mdx_str[n:])
                                n += len(m.group(0))
                                break
                else:                            
                    m = re.search(r'(null|true|false|"[^"]*"),?\s+', mdx_str[n:])
                    if m:
                        if m.group(1) == 'null':
                            val = None
                        elif m.group(1) == 'true':
                            val = True
                        elif m.group(1) == 'false':
                            val = False
                        else:
                            val = m.group(1).strip('"')
                        n += len(m.group(0))
                        params[key] = val
            if mdx_str[n] == '}':
                n += 1
                break

    # content: missing, string, or mdx
    content = []
    while True:
        # print(n, mdx_str[n:n+50])
        if mdx_str[n] == ')':
            n += 1
            break
        elif mdx_str[n] == ',':
            m = re.search(r',\s*', mdx_str[n:])
            n += len(m.group(0))
            if mdx_str[n] == '"':
                m = re.search(r'"(.*?)"(\)|,)', mdx_str[n:])
                c = m.group(1).encode().decode('unicode-escape')
                try:
                    c = c.encode('utf-8').decode('utf-8')
                except:
                    c = c.encode('utf-16', 'surrogatepass').decode('utf-16')
                content.append(c)
                n += len(m.group(0)) - 1
            elif mdx_str[n:n+3] == 'mdx':
                c, x = parse_mdx_str(mdx_str[n:])
                content.append(c)
                n += x
    # print(n)
    return [tag, params, content], n


def render_mdx_html(mdx):
    mdx_html = '<' + mdx[0]
    if mdx[1]:
        for key, val in mdx[1].items():
            if key == 'parentName' or not val:
                continue
            mdx_html += ' {}="'.format(key)
            if isinstance(val, str):
                mdx_html += val
            elif isinstance(val, dict):
                mdx_html += '; '.join([':'.join(list(x)) for x in val.items()])
            mdx_html += '"'
    mdx_html += '>'
    if len(mdx) > 2:
        for mdx_content in mdx[2:]:
            for content in mdx_content:
                if isinstance(content, str):
                    mdx_html += content
                else:
                    mdx_html += render_mdx_html(content)
    if mdx[0] != 'img' or mdx[0] != 'br' or mdx[0] != 'hr':
        mdx_html += '</' + mdx[0] + '>'
    return mdx_html


def render_mdx_layout(mdx_body, netloc='', save_debug=False):
    m = re.search(r'mdx\(".*\)', mdx_body, flags=re.S)
    mdx_str = m.group(0)
    n = 0
    mdx_content = []
    while True:
        mdx, x = parse_mdx_str(mdx_str[n:])
        mdx_content.append(mdx)
        n += x
        if mdx_str[n] == ',':
            m = re.search(r',\s+', mdx_str[n:])                                                                                                                                                                                              
            n += len(m.group(0))
        else:
            break

    if save_debug:
        utils.write_file(mdx_content, './debug/mdx.json')

    mdx_layout = ''
    for mdx in mdx_content:
        mdx_layout += render_mdx_html(mdx)

    if save_debug:
        utils.write_file(mdx_layout, './debug/mdx.html')

    soup = BeautifulSoup(mdx_layout, 'html.parser')

    for el in soup.find_all(['img', 'source']):
        if el['src'].startswith('/'):
            el['src'] = 'https://' + netloc + el['src']

    for el in soup.select('p:has(> img)'):
        it = el.find_next_sibling()
        if it and it.name == 'p' and it.get('classname') and 'caption' in it['classname']:
            caption = it.decode_contents()
            it.decompose()
        else:
            caption = ''
        if el.a:
            link = el.a['href']
        else:
            link = ''
        new_html = utils.add_image(el.img['src'], caption, link=link)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.select('a:has(> img)'):
        it = el.find_next_sibling()
        if it and it.name == 'p' and it.get('classname') and 'caption' in it['classname']:
            caption = it.decode_contents()
            it.decompose()
        else:
            caption = ''
        link = el['href']
        new_html = utils.add_image(el.img['src'], caption, link=link)
        new_el = BeautifulSoup(new_html, 'html.parser')
        el.replace_with(new_el)

    for el in soup.find_all(attrs={"classname": "video-container"}):
        new_html = ''
        if el.source:
            it = el.find_next_sibling()
            if it and it.name == 'p' and it.get('classname') and 'caption' in it['classname']:
                caption = it.decode_contents()
                it.decompose()
            else:
                caption = ''
            new_html = utils.add_video(el.source['src'], el.source['type'], '', caption, use_videojs=True)
        if new_html:
            new_el = BeautifulSoup(new_html, 'html.parser')
            el.replace_with(new_el)
        else:
            logger.warning('unhandled video-container')

    for el in soup.find_all(attrs={"style": re.compile('justifyContent')}):
        el['style'] = el['style'].replace('justifyContent', 'justify-content')

    for el in soup.find_all('blockquote', recursive=False):
        el['style'] = 'border-left:3px solid light-dark(#ccc, #333); margin:1.5em 10px; padding:0.5em 10px;'

    for el in soup.find_all('hr', recursive=False):
        el['style'] = 'margin:2em 0'

    return str(soup)
