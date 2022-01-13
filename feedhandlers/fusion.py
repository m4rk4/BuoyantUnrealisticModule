import pytz, re
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlsplit, quote_plus

import config, utils

import logging
logger = logging.getLogger(__name__)

def get_domain_value(site_url):
  site_html = utils.get_url_html(site_url)
  if site_html:
    soup = BeautifulSoup(site_html, 'html.parser')
    script = soup.find('script', id=re.compile(r'fusion-engine'))
    if script:
      m = re.search(r'\?d=(\d+)', script['src'])
      if m:
        return m.group(1)
  logger.warning('unable to determine site domain number for ' + site_url)
  return ''

def process_content_element(element, url, func_resize_image, gallery=None):
  default_image_width = 1000
  split_url = urlsplit(url)

  element_html = ''
  if element['type'] == 'text' or element['type'] == 'paragraph':
    # Filter out ad content
    if not re.search(r'amzn\.to|fanatics\.com|joinsubtext\.com|lids\.com|nflshop\.com', element['content'], flags=re.I):
      element_html += '<p>{}</p>'.format(element['content'])

  elif element['type'] == 'raw_html':
    # Filter out ad content
    if not re.search(r'amzn\.to|fanatics\.com|joinsubtext\.com|lids\.com|nflshop\.com', element['content'], flags=re.I):
      raw_soup = BeautifulSoup(element['content'], 'html.parser')
      if raw_soup.iframe and raw_soup.iframe.get('src'):
        element_html += utils.add_embed(raw_soup.iframe['src'])
      else:
        logger.warning('unhandled raw_html in ' + url)

  elif element['type'] == 'custom_embed':
    if element['subtype'] == 'custom-audio':
      episode = element['embed']['config']['episode']
      poster = '{}/image?height=128&url={}&overlay=audio'.format(config.server, quote_plus(episode['image']))
      element_html += '<div><a href="{}"><img style="float:left; margin-right:8px;" src="{}"/></a><h4>{}</h4><div style="clear:left;"></div><blockquote><small>{}</small></blockquote></div>'.format(episode['audio'], poster, episode['title'], episode['summary'])
    else:
      logger.warning('unhandled custome_embed in ' + url)

  elif element['type'] == 'divider':
    element_html += '<hr />'

  elif element['type'] == 'correction':
    element_html += '<blockquote><b>{}</b><br>{}</blockquote>'.format(element['correction_type'].upper(), element['text'])

  elif element['type'] == 'quote':
    text = ''
    for el in element['content_elements']:
      text += process_content_element(el, url, func_resize_image, gallery)
    if element['subtype'] == 'blockquote':
      element_html += utils.add_blockquote(text)
    elif element['subtype'] == 'pullquote':
      element_html += utils.add_pullquote(text)
    else:
      logger.warning('unhandled quote item type "{}" in {}'.format(element['subtype'], url))

  elif element['type'] == 'header':
    element_html += '<h{0}>{1}</h{0}>'.format(element['level'], element['content'])

  elif element['type'] == 'oembed_response':
    if element['raw_oembed'].get('_id'):
      element_html += utils.add_embed(element['raw_oembed']['_id'])
    elif element['raw_oembed'].get('url'):
      element_html += utils.add_embed(element['raw_oembed']['url'])
    else:
      logger.warning('unknown raw_oembed url for in ' + url)

  elif element['type'] == 'list':
    if element['list_type'] == 'unordered':
      element_html += '<ul>'
    else:
      element_html += '<ol>'
    for it in element['items']:
      if it['type'] == 'text':
        element_html += '<li>{}</li>'.format(it['content'])
      else:
        #element_html += '<li>Unhandled list item type {}</li>'.format(element['type'])
        logger.warning('unhandled list item type "{}" in {}'.format(element['type'], url))              
    if element['list_type'] == 'unordered':
      element_html += '</ul>'
    else:
      element_html += '</ol>'

  elif element['type'] == 'table':
    element_html += '<table><tr>'
    for it in element['header']:
      if isinstance(it, str):
        element_html += '<th>{}</th>'.format(it)
      elif isinstance(it, dict) and it.get('type') and it['type'] == 'text':
        element_html += '<th>{}</th>'.format(it['content'])
      else:
        logger.warning('unhandled table header item type "{}" in {}'.format(element['type'], url))
    element_html += '</tr>'
    for row in element['rows']:
      element_html += '<tr>'
      for it in row:
        if isinstance(it, str):
          element_html += '<td>{}</td>'.format(it)
        elif isinstance(it, dict) and it.get('type') and it['type'] == 'text':
          element_html += '<td>{}</td>'.format(it['content'])
        else:
          logger.warning('unhandled table row item type "{}" in {}'.format(element['type'], url))
      element_html += '</tr>'
    element_html += '</table>'

  elif element['type'] == 'image':
    img_src = func_resize_image(element, default_image_width)
    if img_src:
      if gallery:
        caption = '[{}/{}] '.format(gallery[0], gallery[1])
      else:
        caption = ''
      if element.get('credits_caption_display'):
        caption += element['credits_caption_display']
      else:
        if element.get('caption'):
          caption += element['caption']
        if element.get('credits'):
          if element['credits'].get('by') and element['credits']['by'][0].get('byline'):
            if not element['credits']['by'][0]['byline'] in caption:
              if caption:
                caption += ' '
              caption += '({})'.format(element['credits']['by'][0]['byline'])
      element_html += utils.add_image(img_src, caption)

  elif element['type'] == 'video':
    if 'washingtonpost.com' in split_url.netloc:
      video_json_url = 'https://video-api.washingtonpost.com/api/v1/ansvideos/findByUuid?uuid=' + element['_id']
      video_json = utils.get_url_json(video_json_url)
      if video_json:
        video_json = video_json[0]
    else:
      video_json = element
    if False:
      utils.write_file(video_json, './debug/video.json')
    # Use an mp4 stream closest to default width
    widths = []
    streams = []
    for it in video_json['streams']:
      if it['stream_type'] == 'mp4':
        widths.append(int(it['width']))
        streams.append(it)
    w = widths[min(range(len(widths)), key=lambda i: abs(widths[i]-default_image_width))]
    for stream in streams:
      if int(stream['width']) == w:
        break
    if 'promo_image' in element:
      poster = func_resize_image(element['promo_image'], default_image_width)
    else:
      poster = None
    element_html += utils.add_video(stream['url'], 'video/mp4', poster, element['headlines']['basic'])

  elif element['type'] == 'social_media' and element['sub_type'] == 'twitter':
    # Parse the embedded html code for the Twitter link
    # It's generally the last one, so go in reverse order
    el_soup = BeautifulSoup(element['html'], 'html.parser')
    for el in reversed(el_soup.find_all('a')):
      if '/status/' in el['href']:
        tweet = utils.add_twitter(el['href'])
        if tweet:
          element_html += tweet
          break
        else:
          logger.warning('unable to add tweet {} in {}'.format(el['href'], url))

  elif element['type'] == 'story':
    # This may be Wapo specific
    element_html += '<hr><h2>{}</h2>'.format(element['headlines']['basic'])
    authors = []
    for author in element['credits']['by']:
      authors.append(author['name'])
    byline = re.sub(r'(,)([^,]+)$', r' and\2', ', '.join(authors))
    tz_est = pytz.timezone('US/Eastern')
    dt = datetime.fromisoformat(element['display_date'].replace('Z', '+00:00')).astimezone(tz_est)
    date = '{}. {}, {} {}'.format(dt.strftime('%b'), dt.day, dt.year, dt.strftime('%I:%M %p').lstrip('0'))
    element_html += '<p>by {} (updated {})</p>'.format(byline, date)
    element_html += get_content_html(element, '', func_resize_image, url)

  elif element['type'] == 'interstitial_link':
    pass

  else:
    logger.warning('unhandled element type "{}" in {}'.format(element['type'], url))
  return element_html

def get_content_html(content, lead_image, func_resize_image, url, save_debug=False):
  content_html = ''
  # Add a lead image if it's not in the article (except galleries because those are moved to the end)
  if not (content['content_elements'][0]['type'] == 'image' or (content['content_elements'][0]['type'] == 'oembed_response' and content['content_elements'][0]['subtype'] == 'youtube')):
    if content.get('multimedia_main'):
      if content['multimedia_main']['type'] == 'gallery':
        content_html += process_content_element(content['multimedia_main']['content_elements'][0], url, func_resize_image)
      else:
        content_html += process_content_element(content['multimedia_main'], url, func_resize_image)
    else:
      if lead_image:
        content_html += process_content_element(lead_image, url, func_resize_image)

  gallery_elements = []
  for element in content['content_elements']:
    # Add galleries to the end of the content
    if element['type'] == 'gallery':
      gallery_elements.append(element)
    else:
      content_html += process_content_element(element, url, func_resize_image)

  if content.get('multimedia_main'):
    if content['multimedia_main']['type'] == 'gallery':
      gallery_elements.append(content['multimedia_main'])
  elif content.get('related_content') and content['related_content'].get('galleries'):
    for gallery in content['related_content']['galleries']:
      gallery_elements.append(gallery)

  if len(gallery_elements) > 0:
    content_html += '<h3>Photo Gallery</h3>'
    for gallery in gallery_elements:
      n = 1
      total = len(gallery['content_elements'])
      for element in gallery['content_elements']:
        content_html += process_content_element(element, url, func_resize_image, [n, total])
        n += 1

  # Reuters specific
  if content.get('related_content') and content['related_content'].get('videos'):
    content_html += '<h3>Related Videos</h3>'
    for video in content['related_content']['videos']:
      caption = '<b>{}</b> &mdash; {}'.format(video['title'], video['description'])
      content_html += utils.add_video(video['source']['mp4'], 'video/mp4', video['thumbnail']['renditions']['original']['480w'], caption)
  return content_html