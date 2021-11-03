import json, re
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

def get_content(url, args, save_debug=False):
  if '/wirecutter/' in url:
    return wirecutter.get_content(url, args, save_debug)

  article_html = utils.get_url_html(url)
  if not article_html:
    return None
  if save_debug:
    utils.write_file(article_html, './debug/debug.html')

  m = re.search(r'<script>window\.__preloadedData = (.+);<\/script>', article_html)
  if not m:
    logger.warning('No preloadData found in ' + url)
    return None
  try:
    json_data = json.loads(m.group(1))
  except:
    logger.warning('Error loading json data from ' + url)
    if save_debug:
      utils.write_file(m.group(1), './debug/debug.txt')
    return get_content_from_html(article_html, url, args, save_debug)
  if save_debug:
    utils.write_file(json_data, './debug/debug.json')

  initial_state = json_data['initialState']
  has_audiotranscript = None

  def format_text(block_id):
    nonlocal url
    nonlocal initial_state
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
          logger.warning('Unhandled format type {} in '.format(fmt['typename'], url))
    for tag in start_tags:
      text_html += tag
    if 'text' in block:
      text_html += block['text']
    elif 'text@stripHtml' in block:
      text_html += block['text@stripHtml']
    else:
      logger.warning('No text in block {} in {}'.format(block_id, url))
    for tag in end_tags:
      text_html += tag
    return text_html

  def format_block(block_id, arg1=None):
    nonlocal url
    nonlocal initial_state
    nonlocal has_audiotranscript
    block_html = ''
    block = initial_state[block_id]

    if block['__typename'] == 'Dropzone' or block['__typename'] == 'RelatedLinksBlock' or block['__typename'] == 'EmailSignupBlock' or block['__typename'] == 'HeaderFullBleedTextPosition':
      pass

    elif block['__typename'] == 'TextInline':
      block_html += format_text(block_id)

    elif block['__typename'] == 'TextOnlyDocumentBlock':
      block_html += block['text']
    
    elif block['__typename'] == 'LineBreakInline':
      block_html += '<br />'

    elif block['__typename'] == 'RuleBlock':
      block_html += '<hr />'

    elif block['__typename'] == 'ParagraphBlock' or block['__typename'] == 'DetailBlock':
      block_html += '<p>'
      for content in block['content']:
        block_html += format_block(content['id'])
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
          block_html += format_block(content['id'])
        block_html += '</h{}>'.format(m.group(1))

    elif block['__typename'] == 'BlockquoteBlock':
      quote = ''
      for content in block['content']:
        quote += format_block(content['id'])
      block_html += utils.add_blockquote(quote)

    elif block['__typename'] == 'PullquoteBlock':
      logger.debug('pullquoteblock in ' + url)
      quote = ''
      for content in block['quote']:
        quote += format_block(content['id'])
      block_html += utils.add_pullquote(quote)

    elif block['__typename'] == 'ListBlock':
      if block['style'] == 'UNORDERED':
        block_tag = 'ul'
      else:
        block_tag = 'ol'
      block_html += '<{}>'.format(block_tag)         
      for content in block['content']:
        block_html += format_block(content['id'])
      block_html += '</{}>'.format(block_tag)

    elif block['__typename'] == 'ListItemBlock':
      block_html += '<li>'
      for content in block['content']:
        block_html += format_block(content['id'])
      block_html += '</li>'

    elif block['__typename'] == 'ImageBlock':
      block_html = format_block(block['media']['id'])

    elif block['__typename'] == 'DiptychBlock':
      for key, image in block.items():
        if key.startswith('image'):
          block_html += format_block(image['id'])

    elif block['__typename'] == 'Image':
      caption = []
      if block.get('caption'):
        cap = format_block(block['caption']['id']).strip()
        if cap:
          caption.append(cap)
      if block.get('credit'):
        caption.append('Credit: ' + block['credit'])
      images = []
      for key, crops in block.items():
        if key.startswith('crops('):
          for crop in crops:
            for rendition in initial_state[crop['id']]['renditions']:
              image = {}
              image['url'] = initial_state[rendition['id']]['url']
              image['width'] = initial_state[rendition['id']]['width']
              image['height'] = initial_state[rendition['id']]['height']
              images.append(image)
      image = utils.closest_dict(images, 'width', 1000)
      return utils.add_image(image['url'], ' | '.join(caption))
      
    elif block['__typename'] == 'ImageCrop':
      logger.warning('ImageCrop in ' + url)
      for rendition in block['renditions']:
        block_html = format_block(rendition['id'], arg1)
        if block_html:
          break

    elif block['__typename'] == 'ImageRendition':
      logger.warning('ImageRendition in ' + url)
      block_html = utils.add_image(block['url'])
      if arg1:
        if not arg1 in block['name']:
          block_html = ''

    elif block['__typename'] == 'VideoBlock':
      block_html = format_block(block['media']['id'])

    elif block['__typename'] == 'Video':
      videos = []
      for rendition in block['renditions']:
        video_rendition = initial_state[rendition['id']]
        if 'mp4' in video_rendition['url']:
          video = {}
          video['url'] = video_rendition['url']
          video['width'] = video_rendition['width']
          video['height'] = video_rendition['height']
        videos.append(video)
      video = utils.closest_dict(videos, 'height', 480)
      if video:
        poster_html = format_block(block['promotionalMedia']['id'])
        poster = ''
        m = re.search(r'src="([^"]+)', poster_html)
        if m:
          poster = m.group(1)
        caption = []
        m = re.search(r'<small>(.*)<\/small>', poster_html)
        if m:
          cap = m.group(1).strip()
          if cap:
            caption.append(cap)
        if block.get('summary').strip():
          caption.append(block['summary'].strip())
        return utils.add_video(video['url'], 'video/mp4', poster, ' | '.join(caption))
      else:
        logger.warning('unhandled video in ' + url)

    elif block['__typename'] == 'VideoRendition':
      logger.warning('VideoRendition in ' + url)
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
      block_html += format_block(block['media']['id'])

    elif block['__typename'] == 'Audio':
      #block_html += '<hr />'
      if 'headline' in block:
        block_html += '<h3>{}</h3>'.format(format_block(block['headline']['id']))
      elif 'promotionalHeadline' in block:
        block_html += '<h3>{}</h3>'.format(block['promotionalHeadline'])
      if '.mp3' in block['fileUrl']:
        block_html += '<audio controls><source src="{}" type="audio/mpeg">Your browser does not support the audio element.</audio>'.format(block['fileUrl'])
      else:
        logger.warning('Unsuported audio file {} in {}'.format(block['fileUrl'], url))
        block_html += '<p>Unsuported audio file: <a href="{0}">{0}</a></p>'.format(block['fileUrl'])
      block_html += '<hr />'
      if block.get('transcript'):
        has_audiotranscript = block['transcript']['id']

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
            block_html += '{}<blockquote style="border-left: 3px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px;"><b style="font-size:smaller;">{}</b><br /><i>{}'.format(end_tag, m.group(1), frag['text'])
            end_tag = '</i></blockquote>'
          else:
            block_html += '{}<p><b style="font-size:smaller;">{}</b><br />{}'.format(end_tag, frag['speaker'], frag['text'])
            end_tag = '</p>'
        last_speaker = frag['speaker']

    elif block['__typename'] == 'HeaderBasicBlock' or block['__typename'] == 'HeaderLegacyBlock' or block['__typename'] == 'HeaderMultimediaBlock' or block['__typename'] == 'HeaderFullBleedVerticalBlock' or block['__typename'] == 'HeaderFullBleedHorizontalBlock':
      for key, val in block.items():
        if isinstance(val, dict):
          if re.search(r'byline|fallback|headline|label|timestamp', key):
            continue
          block_html += format_block(val['id'])

    elif block['__typename'] == 'LabelBlock':
      block_html += '<p><small>'
      for content in block['content']:
        block_html += format_block(content['id']).upper()
      block_html += '</small></p>'

    elif block['__typename'] == 'SummaryBlock':
      block_html += '<p><em>'
      for content in block['content']:
        block_html += format_block(content['id'])
      block_html += '</em></p>'

    elif block['__typename'] == 'BylineBlock':
      authors= ''
      for byline in block['bylines']:
        if authors:
          authors += ', '
        authors += format_block(byline['id'])
      block_html += '<h4>{}</h4>'.format(re.sub(r'(,)([^,]+)$', r' and\2', authors))

    elif block['__typename'] == 'Byline':
      authors = []
      for creator in block['creators']:
        author = format_block(creator['id'])
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
      if block.get('displayName'):
        block_html += block['displayName']
      else:
        block_html += ''

    elif block['__typename'] == 'TimestampBlock':
      dt = datetime.fromisoformat(block['timestamp'].replace('Z', '+00:00'))
      block_html += '<p><small>{}. {}, {}</small></p>'.format(dt.strftime('%b'), dt.day, dt.year)

    else:
      logger.warning('Unhandled block type {} in {}'.format(block['__typename'], url))

    return block_html

  split_url = urlsplit(url)
  article_id = ''
  if 'ROOT_QUERY' in initial_state:
    for key, val in initial_state['ROOT_QUERY'].items():
      if split_url.path in key:
        article_id = val['id']

  if not article_id:
    logger.warning('unable to determine article id  in ' + url)
    return None

  item = {}
  item['id'] = article_id
  item['url'] = url
  item['title'] = format_block(initial_state[article_id]['headline']['id'])
  dt = datetime.fromisoformat(initial_state[article_id]['firstPublished'].replace('Z', '+00:00'))
  item['date_published'] = dt.isoformat()
  item['_timestamp'] = dt.timestamp()
  item['_display_date'] = '{}. {}, {}'.format(dt.strftime('%b'), dt.day, dt.year)
  dt = datetime.fromisoformat(initial_state[article_id]['lastModified'].replace('Z', '+00:00'))
  item['date_modified'] = dt.isoformat()
  authors = []
  for byline in initial_state[article_id]['bylines']:
    author = format_block(byline['id'])
    if author:
      authors.append(author)
  if authors:
    item['author'] = {}
    item['author']['name'] = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
  tags = []
  for tag in initial_state[article_id]['timesTags@filterEmpty']:
    tags.append(initial_state[tag['id']]['displayName'])
  if len(tags) > 0:
    item['tags'] = tags
  image = ''
  media = initial_state[article_id].get('promotionalMedia')
  if media:
    if media['typename'] == 'Image':
      image_html = format_block(media['id'])
      m = re.search(r'src="([^"]+)"', image_html)
      image = m.group(1)
    if image:
      item['_image'] = image
  item['summary'] = initial_state[article_id]['summary']

  content_html = ''
  if initial_state[article_id]['__typename'] == 'Video':
    content_html += format_block(article_id)

  if initial_state[article_id].get('sprinkledBody'):
    body_id = initial_state[article_id]['sprinkledBody']['id']
    for block in initial_state[body_id]['content@filterEmpty']:
      content_html += format_block(block['id'])

  if initial_state[article_id].get('transcript'):
    content_html += '<h4>Transcript:</h4><p>{}</p>'.format(initial_state[article_id]['transcript'])

  if has_audiotranscript:
    content_html += '<hr />' + format_block(has_audiotranscript)

  item['content_html'] = content_html
  return item

def get_feed(args, save_debug=False):
  return rss.get_feed(args, save_debug, get_content)