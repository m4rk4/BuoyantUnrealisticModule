import base64, copy, itertools, json, pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit

import utils
from feedhandlers import rss, wirecutter

import logging

logger = logging.getLogger(__name__)


def get_content_from_html(article_html, url, args, save_debug):
    logger.debug('getting content from html for ' + url)

    soup = BeautifulSoup(article_html, 'html.parser')
    article = soup.find('div', class_='rad-story-body')
    if not article:
        logger.warning('unable to find story-body for ' + url)
        return None

    item = {}
    el = soup.find('meta', attrs={"name": "articleid"})
    if el:
        item['id'] = el['content']
    else:
        item['id'] = url

    item['url'] = url

    for el in soup.find_all('script', attrs={"type": "application/ld+json"}):
        ld_json = json.loads(el.string)
        if ld_json.get('@type') and ld_json['@type'] == 'NewsArticle':
            break
        ld_json = None

    if ld_json:
        item['url'] = url
        item['title'] = ld_json['headline']
        dt = datetime.fromisoformat(ld_json['datePublished'].replace('Z', '+00:00'))
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
        dt = datetime.fromisoformat(ld_json['dateModified'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()
        authors = []
        for author in ld_json['author']:
            authors.append(author['name'])
        item['author'] = {}
        item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        image = utils.closest_dict(ld_json['image'], 'width', 800)
        item['_image'] = image['url']
        item['summary'] = ld_json['description']
    else:
        el = soup.find('meta', attrs={"property": "og:title"})
        if el:
            item['title'] = el['content']
        else:
            item['title'] = soup.find('title').get_text()

        el = soup.find('meta', attrs={"name": "byl"})
        if el:
            item['author'] = {}
            item['author']['name'] = el['content'].replace('By ', '')

        el = soup.find('meta', attrs={"name": "image"})
        if el:
            item['_image'] = el['content']

        el = soup.find('meta', attrs={"name": "description"})
        if el:
            item['summary'] = el['content']

    tags = []
    for el in soup.find_all('meta', attrs={"property": "article:tag"}):
        tags.append(el['content'])
    if len(tags) > 0:
        item['tags'] = tags.copy()

    for el in article.find_all(class_=re.compile(r'\bad\b')):
        el.decompose()

    for el in article.find_all(class_=re.compile(r'rad-cover|photo')):
        img = el.find('img')
        if not img:
            continue
        if img.has_attr('class') and 'rad-lazy' in img['class']:
            images = json.loads(img['data-widths'])
            image = utils.closest_dict(images['MASTER'], 'width', 1000)
            img_src = image['url']
        else:
            img_src = img['src']
        it = el.find('rad-caption')
        if it:
            caption = it.get_text().strip()
        else:
            caption = ''
        if img_src:
            el_html = utils.add_image(img_src, caption)
            el.insert_after(BeautifulSoup(el_html, 'html.parser'))
            el.decompose()

    item['content_html'] = str(article)
    return item


def format_text(block_id, initial_state):
    text_html = ''
    block = initial_state[block_id]
    start_tags = []
    end_tags = []
    if 'formats' in block:
        for fmt in block['formats']:
            if fmt['typename'] == 'LinkFormat':
                start_tags.append('<a href="{}">'.format(initial_state[fmt['id']]['url']))
                end_tags.insert(0, '</a>')
            elif fmt['typename'] == 'BoldFormat':
                start_tags.append('<b>')
                end_tags.insert(0, '</b>')
            elif fmt['typename'] == 'ItalicFormat':
                start_tags.append('<i>')
                end_tags.insert(0, '</i>')
            else:
                logger.warning('Unhandled format type {} in block {} '.format(fmt['typename'], block_id))
    for tag in start_tags:
        text_html += tag
    if 'text' in block:
        text_html += block['text']
    elif 'text@stripHtml' in block:
        text_html += block['text@stripHtml']
    else:
        logger.warning('No text in block {}'.format(block_id))
    for tag in end_tags:
        text_html += tag
    return text_html


def format_block(block_id, initial_state, arg1=None, arg2=None):
    logger.debug(block_id)
    audio_transcript = ''
    block_html = ''
    block = initial_state[block_id]

    if block['__typename'] == 'Dropzone' or block['__typename'] == 'RelatedLinksBlock' or block[
        '__typename'] == 'EmailSignupBlock' or block['__typename'] == 'HeaderFullBleedTextPosition':
        pass

    elif block['__typename'] == 'TextInline':
        block_html += format_text(block_id, initial_state)

    elif block['__typename'] == 'TextOnlyDocumentBlock':
        block_html += block['text']

    elif block['__typename'] == 'LineBreakInline':
        block_html += '<br />'

    elif block['__typename'] == 'RuleBlock':
        block_html += '<hr />'

    elif block['__typename'] == 'ParagraphBlock' or block['__typename'] == 'DetailBlock':
        block_html += '<p>'
        for content in block['content']:
            block_html += format_block(content['id'], initial_state)
        block_html += '</p>'

    elif block['__typename'] == 'CreativeWorkHeadline':
        if 'default@stripHtml' in block:
            block_html += block['default@stripHtml']
        else:
            block_html += block['default']

    elif block['__typename'].startswith('Heading'):
        m = re.search(r'Heading(\d)Block', block['__typename'])
        if m:
            block_html += '<h{}>'.format(m.group(1))
            for content in block['content']:
                block_html += format_block(content['id'], initial_state)
            block_html += '</h{}>'.format(m.group(1))

    elif block['__typename'] == 'BlockquoteBlock':
        quote = ''
        for content in block['content']:
            quote += format_block(content['id'], initial_state)
        block_html += utils.add_blockquote(quote)

    elif block['__typename'] == 'PullquoteBlock':
        quote = ''
        for content in block['quote']:
            quote += format_block(content['id'], initial_state)
        block_html += utils.add_pullquote(quote)

    elif block['__typename'] == 'ListBlock':
        if block['style'] == 'UNORDERED':
            block_tag = 'ul'
        else:
            block_tag = 'ol'
        block_html += '<{}>'.format(block_tag)
        for content in block['content']:
            block_html += format_block(content['id'], initial_state)
        block_html += '</{}>'.format(block_tag)

    elif block['__typename'] == 'ListItemBlock':
        block_html += '<li>'
        for content in block['content']:
            block_html += format_block(content['id'], initial_state)
        block_html += '</li>'

    elif block['__typename'] == 'ImageBlock':
        block_html = format_block(block['media']['id'], initial_state)

    elif block['__typename'] == 'DiptychBlock':
        for key, image in block.items():
            if key.startswith('image'):
                block_html += format_block(image['id'], initial_state)

    elif block['__typename'] == 'Image':
        # arg1 == True : return image url
        # arg2 : custom width
        if arg2:
            width = arg2
        else:
            width = 1000
        image = {}
        for key, crops in block.items():
            if key.startswith('crops('):
                horz_images = []
                vert_images = []
                for crop in crops:
                    for rendition in initial_state[crop['id']]['renditions']:
                        image_rendition = initial_state[rendition['id']]
                        image = {}
                        image['url'] = image_rendition['url']
                        if image_rendition.get('width'):
                            image['width'] = image_rendition['width']
                        else:
                            image['width'] = 1
                        if image_rendition.get('height'):
                            image['height'] = image_rendition['height']
                        else:
                            image['height'] = 1
                        if image['width'] >= image['height']:
                            horz_images.append(image)
                        else:
                            vert_images.append(image)
                # Prefer horzontal images over vertical
                if horz_images:
                    image = utils.closest_dict(horz_images, 'width', width)
                elif vert_images:
                    image = utils.closest_dict(vert_images, 'width', width)
        if image:
            captions = []
            if block.get('caption'):
                caption = format_block(block['caption']['id'], initial_state).strip()
                if caption:
                    captions.append(caption)
            if block.get('credit'):
                captions.append('Credit: ' + block['credit'])
            caption = ' | '.join(captions)
            if arg1:
                return image['url'], caption
            return utils.add_image(image['url'], caption)
        else:
            logger.warning('unhandled Image block ' + block_id)

    elif block['__typename'] == 'ImageCrop':
        logger.warning('ImageCrop block ' + block_id)
        for rendition in block['renditions']:
            block_html = format_block(rendition['id'], initial_state, arg1)
            if block_html:
                break

    elif block['__typename'] == 'ImageRendition':
        logger.warning('ImageRendition block ' + block_id)
        block_html = utils.add_image(block['url'])
        if arg1:
            if not arg1 in block['name']:
                block_html = ''

    elif block['__typename'] == 'GridBlock':
        captions = []
        if block.get('caption'):
            block_html += '<h3>{}</h3>'.format(block['caption'])
        if block.get('media'):
            for media in block['media']:
                block_html += format_block(media['id'], initial_state)

    elif block['__typename'] == 'VideoBlock':
        block_html = format_block(block['media']['id'], initial_state)

    elif block['__typename'] == 'Video':
        # arg1 == True : return image url
        # arg2 : custom height
        if arg2:
            height = arg2
        else:
            height = 480
        videos = []
        for rendition in block['renditions']:
            video_rendition = initial_state[rendition['id']]
            if 'mp4' in video_rendition['url']:
                video = {}
                video['url'] = video_rendition['url']
                video['width'] = video_rendition['width']
                video['height'] = video_rendition['height']
            videos.append(video)
        video = utils.closest_dict(videos, 'height', height)
        if video:
            poster, caption = format_block(block['promotionalMedia']['id'], initial_state, True)
            if block.get('summary'):
                if caption:
                    caption = block['summary'] + ' | ' + caption
                else:
                    caption = block['summary']
            if arg1:
                return video['url'], caption
            return utils.add_video(video['url'], 'video/mp4', poster, caption)
        else:
            logger.warning('unhandled Video block ' + block_id)

    elif block['__typename'] == 'VideoRendition':
        logger.warning('VideoRendition block ' + block_id)
        if '.mp4' in block['url'] or '.mov' in block['url']:
            block_html = utils.add_video(block['url'], 'video/mp4')
        # Check for the specified format
        if arg1:
            if block.get('type'):
                if not arg1 in block['type']:
                    block_html = ''
            else:
                if not arg1.replace('_', '.') in block['url']:
                    block_html = ''

    elif block['__typename'] == 'YouTubeEmbedBlock':
        block_html += utils.add_embed('https://www.youtube.com/embed/' + block['youTubeId'])

    elif block['__typename'] == 'TwitterEmbedBlock':
        block_html += utils.add_embed(block['twitterUrl'])

    elif block['__typename'] == 'AudioBlock':
        block_html += format_block(block['media']['id'], initial_state)

    elif block['__typename'] == 'Audio':
        # block_html += '<hr />'
        if 'headline' in block:
            block_html += '<h3>{}</h3>'.format(format_block(block['headline']['id'], initial_state))
        elif 'promotionalHeadline' in block:
            block_html += '<h3>{}</h3>'.format(block['promotionalHeadline'])
        if '.mp3' in block['fileUrl']:
            block_html += '<audio controls><source src="{}" type="audio/mpeg">Your browser does not support the audio element.</audio>'.format(
                block['fileUrl'])
        else:
            logger.warning('Unsuported audio file {} in block {}'.format(block['fileUrl'], block_id))
            block_html += '<p>Unsuported audio file: <a href="{0}">{0}</a></p>'.format(block['fileUrl'])
        block_html += '<hr />'
        if block.get('transcript'):
            audio_transcript = block['transcript']['id']

    elif block['__typename'] == 'AudioTranscript':
        block_html += '<hr /><h3>Audio Transcript</h3><p>'
        last_speaker = ''
        end_tag = '</p>'
        for transcript in block['transcriptFragment']:
            frag = initial_state[transcript['id']]
            if frag['speaker'] == last_speaker:
                block_html += ' ' + frag['text']
            else:
                m = re.search(r'^\^(.*)\^$', frag['speaker'])
                if m:
                    block_html += '{}<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;"><b style="font-size:smaller;">{}</b><br /><i>{}'.format(
                        end_tag, m.group(1), frag['text'])
                    end_tag = '</i></blockquote>'
                else:
                    block_html += '{}<p><b style="font-size:smaller;">{}</b><br />{}'.format(end_tag, frag['speaker'],
                                                                                             frag['text'])
                    end_tag = '</p>'
            last_speaker = frag['speaker']

    elif block['__typename'] == 'HeaderBasicBlock' or block['__typename'] == 'HeaderLegacyBlock' or block[
        '__typename'] == 'HeaderMultimediaBlock' or block['__typename'] == 'HeaderFullBleedVerticalBlock' or block[
        '__typename'] == 'HeaderFullBleedHorizontalBlock':
        for key, val in block.items():
            if isinstance(val, dict):
                if re.search(r'byline|fallback|headline|label|timestamp', key) and not arg1:
                    continue
                block_html += format_block(val['id'], initial_state)

    elif block['__typename'] == 'LabelBlock':
        block_html += '<p><small>'
        for content in block['content']:
            block_html += format_block(content['id'], initial_state).upper()
        block_html += '</small></p>'

    elif block['__typename'] == 'SummaryBlock':
        block_html += '<p><em>'
        for content in block['content']:
            block_html += format_block(content['id'], initial_state)
        block_html += '</em></p>'

    elif block['__typename'] == 'BylineBlock':
        authors = ''
        for byline in block['bylines']:
            if authors:
                authors += ', '
            authors += format_block(byline['id'], initial_state)
        block_html += '<h4>{}</h4>'.format(re.sub(r'(,)([^,]+)$', r' and\2', authors))

    elif block['__typename'] == 'Byline':
        authors = []
        for creator in block['creators']:
            author = format_block(creator['id'], initial_state)
            if author:
                authors.append(author)
        if block.get('prefix'):
            byline = block['prefix'] + ' '
        else:
            byline = ''
        if authors:
            byline += re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        else:
            if block.get('renderedRepresentation'):
                byline += re.sub(r'^By ', '', block['renderedRepresentation'])
        block_html += byline

    elif block['__typename'] == 'Person':
        name = ''
        if block.get('displayName'):
            name = block['displayName']
        image = ''
        if block.get('promotionalMedia') and block['promotionalMedia']['typename'] == 'Image':
            image, caption = format_block(block['promotionalMedia']['id'], initial_state, True, 64)
        if arg1:
            return name, image
        block_html += name

    elif block['__typename'] == 'TimestampBlock':
        dt = datetime.fromisoformat(block['timestamp'].replace('Z', '+00:00'))
        if arg1:
            return dt
        block_html += '<p><small>{}. {}, {}</small></p>'.format(dt.strftime('%b'), dt.day, dt.year)

    elif block['__typename'] == 'LegacyCollectionGrouping':
        for container in block['containers']:
            block_html += format_block(container['id'], initial_state)

    elif block['__typename'] == 'LegacyCollectionContainer':
        for relation in block['relations']:
            block_html += format_block(relation['id'], initial_state)

    elif block['__typename'] == 'LegacyCollectionRelation':
        block_html += format_block(block['asset']['id'], initial_state)

    elif block['__typename'] == 'LegacyCollection':
        for key, val in block.items():
            if 'highlights' in key:
                block_html += format_block(val['id'], initial_state)

    elif block['__typename'] == 'AssetsConnection':
        if block.get('edges'):
            for edge in block['edges']:
                block_html += format_block(edge['id'], initial_state)
        else:
            logger.debug('AssetsConnection with no edges in ' + block_id)

    elif block['__typename'] == 'AssetsEdge':
        if block.get('node'):
            block_html += format_block(block['node']['id'], initial_state)
        elif block.get('node@filterEmpty'):
            block_html += format_block(block['node@filterEmpty']['id'], initial_state)
        else:
            logger.warning('unhandled AssetsEdge ' + block_id)

    elif block['__typename'] == 'Capsule':
        if block.get('body'):
            block_html += format_block(block['body']['id'], initial_state)
        else:
            logger.warning('unhandled Capsule with no body' + block_id)

    elif block['__typename'] == 'DocumentBlock':
        for key, val in block.items():
            if key.startswith('content@'):
                for content in val:
                    block_html += format_block(content['id'], initial_state)

    elif block['__typename'] == 'InteractiveBlock':
        if block.get('media'):
            block_html += format_block(block['media']['id'], initial_state)
        else:
            logger.warning('unhandled InteractiveBlock ' + block_id)

    elif block['__typename'] == 'EmbeddedInteractive':
        embed_html = ''
        soup = BeautifulSoup(block['html'], 'html.parser')
        el = soup.find('script', attrs={"type": "application/cri"})
        if el:
            embed_json = json.loads(el.string)
            # utils.write_file(embed_json, './debug/gallery.json')
            if embed_json.get('slides'):
                for slide in embed_json['slides']:
                    if slide['__typename'] == 'Image':
                        horz_images = []
                        vert_images = []
                        for crop in slide['crops']:
                            for rendition in crop['renditions']:
                                if rendition['width'] >= rendition['height']:
                                    horz_images.append(rendition)
                                else:
                                    vert_images.append(rendition)
                        if horz_images:
                            image = utils.closest_dict(horz_images, 'width', 1000)
                        else:
                            image = utils.closest_dict(horz_images, 'width', 1000)
                        captions = []
                        if slide.get('caption'):
                            captions.append(slide['caption'])
                        if slide.get('credit'):
                            captions.append(slide['credit'])
                        embed_html += utils.add_image(image['url'], ' | '.join(captions))
                    else:
                        logger.warning(
                            'unhandled EmbeddedInteractive slide type {} in {}'.format(slide['__typename'], block_id))
        if embed_html:
            block_html += embed_html
        else:
            embed_html = '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>{}</body></html>'.format(block['html'])
            embed_b64 = base64.b64encode(embed_html.encode('utf-8'))
            block_html += '<h4><a href="data:text/html;base64,{}">Embedded content</a></h4>'.format(
                embed_b64.decode('utf-8'))

    elif block['__typename'] == 'AssociatedLegacyCollectionAssetBlock':
        if block.get('asset'):
            block_html += format_block(block['asset']['id'], initial_state)

    elif block['__typename'] == 'AssociatedStoryline':
        block_html += format_block(block['storyline']['id'], initial_state)

    elif block['__typename'] == 'StorylinePrimaryAsset':
        block_html += '<a href="{}">{}</a>'.format(initial_state[block['asset']['id']]['url'], block['displayName'])

    elif block['__typename'] == 'StorylineHubAsset':
        return initial_state[block['asset']['id']]['url']

    elif block['__typename'] == 'StorylinePrimaryAsset':
        return '<a href="{}">{}</a>'.format(initial_state[block['asset']['id']]['url'], block['displayName'])

    elif block['__typename'] == 'Storyline':
        block_html += '<div class="Storyline">'

        if block.get('hubAssets'):
            block_html += '<h3><a href="{}">{}</a></h3>'.format(
                format_block(block['hubAssets'][0]['id'], initial_state), block['displayName'])
            # Not sure what additional hubAssets are used for
            if len(block['hubAssets']) > 1:
                logger.warning('unhandled hubAssets in ' + block_id)
        else:
            block_html += '<h3>{}</h3>'.format(block['displayName'])

        if block.get('primaryAssets'):
            block_html += '<ul>'
            for asset in block['primaryAssets']:
                block_html += '<li>{}</li>'.format(format_block(asset['id'], initial_state))
            block_html += '</ul>'

        if block.get('experimentalJsonBlob'):
            json_blob = json.loads(block['experimentalJsonBlob'])
            utils.write_file(json_blob, './debug/blob.json')
            for data in json_blob['data']:
                for data_data in data['data']:
                    if data_data['type'] == 'lede':
                        for data_data_data in data_data['data']:
                            if data_data_data['type'] == 'text':
                                block_html += '<p>{}</p>'.format(data_data_data['value'])
                            else:
                                logger.debug(
                                    'unhandled experimentalJsonBlob data type {}'.format(data_data_data['type']))
                    elif data_data['type'] == 'context':
                        block_html += '<h4>{}</h4><ul>'.format(data_data['data']['title'])
                        for item in data_data['data']['items']:
                            block_html += '<li><b>{}</b><br/>{}</li>'.format(item['subtitle'], item['text'])
                        block_html += '</ul>'
                    elif data_data['type'] == 'topLinks':
                        block_html += '<h4>{}</h4>{}<ul>'.format(data_data['data']['title'], data_data['data']['leadIn'])
                        for item in data_data['data']['bulletedList']:
                            block_html += '<li>{}</li>'.format(item)
                        block_html += '</ul>'
                    elif data_data['type'] == 'guide':
                        block_html += '<h4>{}</h4>{}'.format(data_data['data']['title'], data_data['data']['leadIn'])
                        for section in data_data['data']['sections']:
                            if section['section'][0]['type'] == 'bulletedList':
                                block_html += '<ul>'
                                for item in section['section'][0]['value']:
                                    block_html += '<li>{}</li>'.format(item)
                                block_html += '</ul>'
                            else:
                                logger.warning('unhandled experimentalJsonBlob guide section type {}'.format(section['section'][0]['type']))
                    else:
                        logger.debug('unhandled experimentalJsonBlob data type {}'.format(data_data['type']))
            block_html += '<hr/></div>'

    else:
        logger.warning('Unhandled block type {} in {}'.format(block['__typename'], block_id))

    return block_html


def get_legacy_collection_group(block_id, initial_state):
    # logger.debug(block_id)
    block = initial_state[block_id]
    items = []
    for container in block['containers']:
        for relation in initial_state[container['id']]['relations']:
            asset = initial_state[relation['id']]['asset']
            item = get_block_item(asset['id'], initial_state)
            if item:
                items.append(item)
    return items


def get_assets_connection(block_id, initial_state):
    # logger.debug(block_id)
    block = initial_state[block_id]
    items = []
    for edge in block['edges']:
        node = initial_state[edge['id']]['node']
        item = get_block_item(node['id'], initial_state)
        if item:
            items.append(item)
    return items


def get_block_item(block_id, initial_state):
    # logger.debug(block_id)
    block = initial_state[block_id]

    item = {}
    if block.get('id'):
        item['id'] = block['id']
    else:
        item['id'] = block_id

    if block.get('url'):
        item['url'] = block['url']

    if block.get('headline'):
        item['title'] = format_block(block['headline']['id'], initial_state)

    dt = None
    if block.get('firstPublished'):
        dt = datetime.fromisoformat(block['firstPublished'].replace('Z', '+00:00'))
    elif block.get('timestampBlock'):
        dt = format_block(block['timestampBlock']['id'], initial_state, True)
    if dt:
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        dt_est = dt.astimezone(pytz.timezone('US/Eastern'))
        item['_display_date'] = '{}. {}, {}, {}:{} {}'.format(dt_est.strftime('%b'), dt_est.day, dt_est.year,
                                                              int(dt_est.strftime('%I')), dt_est.strftime('%M'),
                                                              dt_est.strftime('%p').lower())
        # item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

    if block.get('lastModified'):
        dt = datetime.fromisoformat(block['lastModified'].replace('Z', '+00:00'))
        item['date_modified'] = dt.isoformat()

    image = ''
    item['author'] = {}
    if block.get('bylines'):
        authors = []
        for byline in block['bylines']:
            byline_block = initial_state[byline['id']]
            if byline_block.get('creators'):
                for creator in byline_block['creators']:
                    author, image = format_block(creator['id'], initial_state, True)
                authors.append(author)
        if authors:
            item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
        if len(authors) > 1 or not image:
            image = 'https://static01.nyt.com/images/icons/t_logo_150_black.png'
    if not item['author'].get('name'):
        item['author'] = {"name": "New York Times"}
        image = 'https://static01.nyt.com/images/icons/t_logo_150_black.png'
    item['author']['image'] = image

    if block.get('timesTags@filterEmpty'):
        tags = []
        for tag in block['timesTags@filterEmpty']:
            tags.append(initial_state[tag['id']]['displayName'])
        if len(tags) > 0:
            item['tags'] = tags

    if block.get('promotionalMedia'):
        if block['promotionalMedia']['typename'] == 'Image':
            img_src, caption = format_block(block['promotionalMedia']['id'], initial_state, True)
            item['_image'] = img_src

    if block.get('summary'):
        item['summary'] = block['summary']

    content_html = ''
    block = initial_state[block_id]
    if block['__typename'] == 'Video':
        content_html += format_block(block_id, initial_state)

    if block.get('sprinkledBody'):
        for blk in initial_state[block['sprinkledBody']['id']]['content@filterEmpty']:
            content_html += format_block(blk['id'], initial_state)

    if block.get('body'):
        content_html += format_block(block['body']['id'], initial_state)

    if block.get('storylines'):
        content_html += '<h2>Storylines</h2>'
        for blk in block['storylines']:
            content_html += format_block(blk['id'], initial_state)

    sub_items = []
    if block.get('groupings'):
        content_html += '<h2>Groupings</h2>'
        for block_group in block['groupings']:
            group = initial_state[block_group['id']]
            if group['__typename'] == 'LegacyCollectionGrouping':
                for group_container in group['containers']:
                    container = initial_state[group_container['id']]
                    if container['name'] == 'promos' or container['name'] == 'footer':
                        continue
                    for container_relation in container['relations']:
                        relation = initial_state[container_relation['id']]
                        asset = get_block_item(relation['asset']['id'], initial_state)
                        if asset:
                            if asset.get('title'):
                                print(asset['title'])
                            else:
                                print(asset['id'])
                            if asset.get('_timestamp'):
                                if not [it for it in sub_items if it['_timestamp'] == asset['_timestamp']]:
                                    sub_items.append(asset)
                            else:
                                content_html += asset['content_html'] + '<hr/>'
            else:
                logger.warning('unhandled group type {} in {}'.format(group['typename'], block_id))

    if block.get('highlights'):
        content_html += '<h2>Highlights</h2>'
        highlights = initial_state[block['highlights']['id']]
        if highlights['__typename'] == 'AssetsConnection':
            for edge in highlights['edges']:
                node = get_block_item(initial_state[edge['id']]['node']['id'], initial_state)
                if node and not [it for it in sub_items if it['_timestamp'] == node['_timestamp']]:
                    sub_items.append(node)
        else:
            logger.warning('unhandled highlights type {} in {}'.format(highlights['__typename'], highlights['id']))

    for key, val in block.items():
        if key.startswith('stream('):
            content_html += '<h2>Stream</h2>'
            stream = initial_state[val['id']]
            if stream['__typename'] == 'AssetsConnection':
                for stream_edge in stream['edges']:
                    edge = initial_state[stream_edge['id']]
                    if edge.get('node'):
                        node = get_block_item(edge['node']['id'], initial_state)
                    elif edge.get('node@filterEmpty'):
                        node = get_block_item(edge['node@filterEmpty']['id'], initial_state)
                    else:
                        node = None
                    if node and not [it for it in sub_items if it['_timestamp'] == node['_timestamp']]:
                        sub_items.append(node)
            else:
                logger.warning('unhandled stream type {} in {}'.format(stream['typename'], stream['id']))

    if block.get('associatedAssets'):
        content_html += '<h2>Associated Assets</h2>'
        for block_asset in block['associatedAssets']:
            asset = get_block_item(initial_state[block_asset['id']]['asset']['id'], initial_state)
            if asset:
                if asset.get('_timestamp'):
                    if not [it for it in sub_items if it['_timestamp'] == asset['_timestamp']]:
                        sub_items.append(asset)
                else:
                    content_html += asset['content_html']

    if sub_items:
        # uniq_items = {it['_timestamp']: it for it in sub_items}.values()
        # sub_items = sorted(sub_items, key=lambda i: i['_timestamp'], reverse=True)
        content_html += '<h3>Here\'s what you need to know:</h3><ul>'
        for it in sub_items:
            if it.get('url'):
                content_html += '<li><a href="{}">{}</a></li>'.format(it['url'], it['title'])
            else:
                content_html += '<li>{}</li>'.format(it['title'])
        content_html += '</ul>'

    # utils.write_file(sub_items, './debug/items.json')

    item['content_html'] = content_html

    if False:
        soup = BeautifulSoup(content_html, 'html.parser')
        new_soup = BeautifulSoup('', 'html.parser')
        for el in soup.find_all(class_=['DocumentBlock', 'Storyline'], recursive=False):
            new_soup.append(copy.copy(el))

        # Remove duplicate articles (based on timestamps) and sort with most recent first
        timestamps = []
        for el in soup.find_all(class_=['Article', 'ReporterUpdate']):
            timestamps.append(float(el['timestamp']))
        if timestamps:
            timestamps = sorted(list(set(timestamps)), reverse=True)
            for ts in timestamps:
                el = soup.find(timestamp=str(ts))
                new_soup.append(copy.copy(el))

            dt = datetime.fromtimestamp(timestamps[0])
            item['date_published'] = dt.isoformat()
            item['_timestamp'] = dt.timestamp()
            item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)

        # utils.write_file(str(new_soup), './debug/content.html')
        content_html = str(new_soup)

        if block.get('transcript'):
            content_html += '<h4>Transcript:</h4><p>{}</p>'.format(block['transcript'])

        # if audio_transcript:
        #  content_html += '<hr />' + format_block(audio_transcript, initial_state)
    return item


def get_content(url, args, save_debug=False):
    if '/wirecutter/' in url:
        return wirecutter.get_content(url, args, save_debug)

    article_html = utils.get_url_html(url, user_agent='googlebot')
    if not article_html:
        return None
    if save_debug:
        utils.write_file(article_html, './debug/debug.html')

    m = re.search(r'<script>window\.__preloadedData = (.+);</script>', article_html)
    if not m:
        logger.warning('No preloadData found in ' + url)
        return None
    if save_debug:
        utils.write_file(m.group(1), './debug/debug.txt')
    try:
        json_data = json.loads(m.group(1).replace(':undefined', ':""'))
    except:
        logger.warning('Error loading json data from ' + url)
        if save_debug:
            utils.write_file(m.group(1), './debug/debug.txt')
        return get_content_from_html(article_html, url, args, save_debug)
    if save_debug:
        utils.write_file(json_data, './debug/debug.json')

    initial_state = json_data['initialState']

    split_url = urlsplit(url)
    root_id = ''
    if 'ROOT_QUERY' in initial_state:
        for key, val in initial_state['ROOT_QUERY'].items():
            if split_url.path in key:
                root_id = val['id']
    if not root_id:
        logger.warning('unable to determine article id  in ' + url)
        return None

    item = get_block_item(root_id, initial_state)
    return item


def get_feed(args, save_debug=False):
    return rss.get_feed(args, save_debug, get_content)
