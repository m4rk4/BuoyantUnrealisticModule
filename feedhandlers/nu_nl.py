import json, re
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_cffi_requests
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit

import config, utils

import logging

logger = logging.getLogger(__name__)


def get_content(url, args, site_json, save_debug=False):
    gql_url = 'https://www.nu.nl/api/f1/graphql'
    gql_data = {
        "operationName": "ScreenByUrl",
        "variables": {
            "url": utils.clean_url(url)
        },
        "extensions": {
            "persistedQuery": {
                "sha256Hash": "8ce911c7ee9543f71f4ae32ca41682d1a7d61048c6ef9cd6c03426218a898af3",
                "version": 1
            }
        }
    }
    # "query": "query ScreenByUrl ($url: Url!) { screenByUrl (url: $url) { __typename commentsCount commentsEnabled id schemaOrgString screenCanonicalUrl sectionTheme title updatedAt actions{ __typename hide {...LocalAction} show {...LocalAction} } advertisementData{ __typename key value } firstBlockPage{ __typename blocks {...Block} sideLoadedBlocks {...Block} sidebarBlocks {...Block} topzoneBlocks {...Block} } grids{ __typename id narrowColumnCount wideColumnCount } httpResponse{ __typename redirectUrl statusCode } primaryColorTheme {...ColorTheme} screenMetadata{ __typename key value } screenOgData{ __typename key value } trackers{ __typename show {...TrackingEvent} } twitterCardData{ __typename key value } variables {...Variable} } } fragment Variable on Variable { __typename name value } fragment TrackingEvent on TrackingEvent { __typename trackOnceId timerSettings{ __typename minimalTimeThreshold startPolicy stopPolicy timerId timerLeavePolicy timerPolicy } ... on CookieEvent { cookieMaxAge cookieName cookieOperation cookieValue } ... on CxenseEvent { appPlatform category loc shareUrl title } ... on DataAttributesEvent { fields{ __typename key value } } ... on DataLayerScreenViewEvent { eventName fields{ __typename key value } } ... on GTMTrackingEvent { eventName fields{ __typename key value } } ... on GenericEvent { eventName } ... on GoogleEvent { action alibi category label value customDimensions {...GoogleIndexedParam} customMetrics {...GoogleIndexedParam} customParams{ __typename key value } } } fragment GoogleIndexedParam on GoogleIndexedParam { __typename index value } fragment ColorTheme on ColorTheme { __typename id } fragment Block on Block { __typename groupIds id displayRule{ __typename ... on VariableEqualsRule { variableName variableValue } ... on VariableNotEqualsRule { variableName variableValue } } trackers {...BlockTrackers} ... on AudioBlock { embedUrl } ... on BannerBlock { showOnDesktop showOnMobile slotIndex slotName } ... on ButtonBarBlock { buttonBarPresentationStyle buttonsPresentationStyle buttons {...BarButton} } ... on CarouselLinkBlock { carouselLinkFlavor legacySlideshowName viewAspectRatio links {...Link} } ... on ClientSideTimelineBlock { timelineId } ... on CommentBlock { likes replies commentText {...StyledText} dateLabel {...StyledText} likesText {...StyledText} repliesText {...StyledText} respondText {...StyledText} target {...TargetInception} username {...StyledText} usernameLabel{ __typename text {...StyledText} } } ... on ContainerBlock { sideLoadedBlockIds webContainerFlavor{ __typename ... on ArticleMetaContainer { location } ... on ContentListContainer { header template theme GTMTrackers {...GTMTrackers} trackers {...BlockTrackers} } ... on StyledWebContainer { cssClass tag GTMTrackers {...GTMTrackers} attributes{ __typename key value } trackers {...BlockTrackers} } } } ... on DetailBlock { summary updatedAt icon {...Image} title {...StyledText} } ... on EmbedBlock { blockFlavor{ __typename ... on InfographicEmbedBlockFlavor { copyright heightHint provider providerUrl url usePym themedUrl{ __typename dark light } } ... on TrackingPixelEmbedBlockFlavor { embedCode } ... on TrackingPixelFlavor { url } ... on TwitterEmbedBlockFlavor { align cards conversation tweetId width } ... on WebEmbedBlockFlavor { embedCode heightHint url } } } ... on ErrorBlock { errorIdentifier message GTMTrackers {...GTMTrackers} } ... on FloatingButtonsBarBlock { buttonBarPresentationStyle buttonsPresentationStyle buttons {...BarButton} } ... on FormElementBlock { groupId inputValue borderColorTheme {...ColorTheme} fieldLabel {...StyledText} formElementFlavor{ __typename ... on TextFieldFlavor { borderWidth cornerRadius maxlength placeholder borderColorTheme {...ColorTheme} placeholderText {...StyledText} } } target {...TargetInception} value {...StyledText} } ... on HeaderBlock { headerLevel theme subtitle {...StyledText} target {...TargetInception} title {...StyledText} titlePrefixIcon {...Image} titleSuffixIcon {...Image} } ... on ImageBlock { imageStyle image {...Image} imageFlavor{ __typename ... on ArticleHeadImageFlavor { label {...StyledText} title {...StyledText} } ... on FigureImageFlavor { caption {...StyledText} copyright {...StyledText} } ... on SizedImageFlavor { height width } } target {...TargetInception} title {...StyledText} } ... on LinkBlock { grid template type link {...Link} } ... on MenuItemBlock { active icon {...Image} target {...TargetInception} title {...StyledText} } ... on ScoreboardBlock { activeWidget {...ScoreboardBlockActive} activeWidgets {...ScoreboardBlockActive} widgetSets{ __typename widgetSetId icon {...Image} title {...StyledText} widgets{ __typename ... on GraceNoteWidget { competitionId editionId eventPhaseId gracenoteWidgetId leagueId matchId season widgetId title {...StyledText} } } } } ... on SourceBlock { icon {...Image} target {...TargetInception} title {...StyledText} } ... on TextBlock { readStateId textRole styledText {...StyledText} styledTexts {...StyledText} textFlavor{ __typename ... on IconTextFlavor { linkAlignment prefixIcon {...Image} suffixIcon {...Image} } ... on LabelTextFlavor { backgroundColor {...ColorTheme} prefixIcon {...Image} suffixIcon {...Image} } ... on LabeledListItemTextFlavor { leftPadding label {...StyledText} } ... on ListItemTextFlavor { leftPadding bulletColorTheme {...ColorTheme} } ... on SizedImageTextFlavor { linkAlignment prefixImage {...Image} prefixImageSize {...ImageSize} suffixImage {...Image} suffixImageSize {...ImageSize} } ... on SponsoredByTextFlavor { brandIcon {...Image} } } } ... on VideoBlock { caption createdAt duration isLivestream mediaId previewImage {...Image} title {...StyledText} videoFlavor{ __typename ... on ArticleHeaderVideoFlavor { caption createdAt } } videoPlayerFlavor{ __typename ... on EmbedPlayerFlavor { embedCode url } ... on JWPlayerFlavor { adSectionName disableAds orientation playlist commentsButton{ __typename numberOfComments icon {...Image} target {...TargetInception} } pauseIcon {...Image} playIcon {...Image} shareButton{ __typename icon {...Image} target {...TargetInception} } toggleCaptionButton{ __typename collapse {...IconText} expand {...IconText} } } ... on YouTubePlayerFlavor { url } } } ... on WidgetBarBlock { label updatedAt widgetBarStyle widgetBarIcons{ __typename accessibilityTitle label image {...Image} target {...TargetInception} } } ... on WidgetLinkBlock { link {...Link} } } fragment Link on Link { __typename groupIds linkFlavor{ __typename ... on ButtonLinkFlavor { alignment borderWidth cornerRadius linkWidth backgroundColorTheme {...ColorTheme} borderColorTheme {...ColorTheme} prefixIcon {...Image} suffixIcon {...Image} } ... on CTALinkFlavor { cta {...StyledText} icon {...Image} title {...StyledText} } ... on CTAWithLargeTextLinkFlavor { body {...StyledText} cta {...StyledText} icon {...Image} } ... on ImageLinkFlavor { image {...Image} } ... on LargeArticleLinkFlavor { estimatedDuration publishedAt icon {...Image} image {...Image} label {...StyledText} labelSuffixIcon {...Image} } ... on MoreLinkFlavor { theme chevronColorTheme {...ColorTheme} } ... on RightIconButtonLinkFlavor { buttonIcon {...Image} icon {...Image} label {...StyledText} } ... on SmallArticleLinkFlavor { estimatedDuration isPartner publishedAt brandIcon {...Image} byline {...StyledText} icon {...Image} image {...Image} label {...StyledText} } ... on SubtitleLinkFlavor { prefixIcon {...Image} subtitle {...StyledText} suffixIcon {...Image} } ... on TagButtonLinkFlavor { subscribed icon {...Image} } ... on TextLinkFlavor { linkWidth prefixIcon {...Image} suffixIcon {...Image} } ... on TimelineLinkFlavor { estimatedDuration brandIcon {...Image} byline {...StyledText} colorTheme {...ColorTheme} icon {...Image} image {...Image} label {...StyledText} } ... on ToggleLinkFlavor { enabled icon {...Image} subTitle {...StyledText} } ... on VideoLinkFlavor { duration {...StyledText} icon {...Image} image {...Image} } } target {...TargetInception} title {...StyledText} } fragment StyledText on StyledText { __typename text textType linkTargets{ __typename id url target {...TargetInception} } } fragment Target on Target { __typename GTMTrackers {...GTMTrackers} trackers{ __typename activate {...TrackingEvent} } ... on PushSubscribeTarget { pushTag successMessage } } fragment TargetInception on Target { ...Target ... on ActionMenuTarget { actionMenuId } ... on AudioTarget { audioId audioType createdAt duration id shareUrl title updatedAt url thumbnailMedia {...Image} } ... on ContributionTarget { articleId } ... on FormSubmitTarget { groupId tagIds } ... on InternalBlockTarget { blockId } ... on JWPlayerVideoTarget { shareUrl } ... on LoginTarget { failureTrackers {...TrackingEvent} successTrackers {...TrackingEvent} } ... on LogoutTarget { failureTrackers {...TrackingEvent} successTrackers {...TrackingEvent} } ... on PushSubscribeTarget { pushTag successMessage } ... on RemoteTarget { action permissions } ... on ScreenTarget { targetId url } ... on SetVariablesTarget { variables {...Variable} } ... on ShareTarget { shareText } ... on SlideshowTarget { id slideId } ... on UrlTarget { relation url } ... on VideoTarget { shareUrl } } fragment Image on Image { __typename copyright description id title url viewAspectRatio ... on GenericImage { mediaId } ... on Graphic { name tintColor {...ColorTheme} } ... on LottieAnimation { autoplay cornerRadius count loop repeatMode speed src backgroundColorTheme {...ColorTheme} } } fragment GTMTrackers on GTMTrackers { __typename click{ __typename action category contentId element isAlgorithmicItem itemId itemLabel itemUrl label list position relevance teaserTitle teaserType } view{ __typename event data{ __typename key value } } } fragment IconText on IconText { __typename text icon {...Image} } fragment ImageSize on ImageSize { __typename height width } fragment ScoreboardBlockActive on ScoreboardBlockActive { __typename widgetId widgetSetId } fragment BarButton on BarButton { __typename linkWidth backgroundColorTheme {...ColorTheme} target {...TargetInception} title {...StyledText} } fragment BlockTrackers on BlockTrackers { __typename click {...TrackingEvent} show {...TrackingEvent} } fragment LocalAction on LocalAction { __typename executeOnceId ... on LiveDataConnectionAction { actionHandler liveDataEventSource{ __typename ... on FirebaseRealTimeDataEventSource { connectionString itemId addTarget {...TargetInception} removeTarget {...TargetInception} updateTarget {...TargetInception} } } } }"
    # https://myprivacy-static.dpgmedia.net/integrator-config/nu-nl-nl.json
    r = curl_cffi_requests.post(gql_url, json=gql_data, impersonate="chrome", proxies=config.proxies)
    print(r.status_code)
    if r.status_code != 200:
        print(r.text)
        return None
    gql_json = r.json()
    # gql_json = utils.post_url(gql_url, json_data=gql_data, use_proxy=True, use_curl_cffi=True)
    # if not gql_json:
    #     return None
    if save_debug:
        utils.write_file(gql_json, './debug/debug.json')
    screen_json = gql_json['data']['screenByUrl']

    item = {}
    item['id'] = screen_json['id']
    item['url'] = screen_json['screenCanonicalUrl']

    data = next((it for it in screen_json['screenOgData'] if it['key'] == 'og:title'), None)
    if data:
        item['title'] = data['value']
    else:
        item['title'] = screen_json['title']

    data = next((it for it in screen_json['screenMetadata'] if it['key'] == 'article:published_time'), None)
    if data:
        dt = datetime.fromisoformat(data['value']).astimezone(timezone.utc)
        item['date_published'] = dt.isoformat()
        item['_timestamp'] = dt.timestamp()
        item['_display_date'] = utils.format_display_date(dt)

    data = next((it for it in screen_json['firstBlockPage']['sideLoadedBlocks'] if it['__typename'] == 'TextBlock' and it['textRole'] == 'ARTICLE_AUTHOR'), None)
    if data:
        item['author'] = {
            "name": data['styledText']['text']
        }
    else:
        item['author'] = {
            "name": "NU.nl"
        }
    item['authors'] = []
    item['authors'].append(item['author'])

    data = next((it for it in screen_json['screenMetadata'] if it['key'] == 'article:updated_time'), None)
    if data:
        dt = datetime.fromisoformat(data['value']).astimezone(timezone.utc)
        item['date_modified'] = dt.isoformat()

    data = next((it for it in screen_json['screenMetadata'] if it['key'] == 'keywords'), None)
    if data:
        item['tags'] = [it.strip() for it in data['value'].split(',')]

    data = next((it for it in screen_json['screenOgData'] if it['key'] == 'og:image'), None)
    if data:
        item['image'] = data['value']

    data = next((it for it in screen_json['screenMetadata'] if it['key'] == 'description'), None)
    if data:
        item['summary'] = data['value']

    data = next((it for it in screen_json['advertisementData'] if it['key'] == 'pageType'), None)
    if data:
        if data['value'] == 'video':
            data = next((it for it in screen_json['firstBlockPage']['blocks'] if it['__typename'] == 'VideoBlock'), None)
            if data:
                if 'date_published' not in item:
                    dt = datetime.fromisoformat(data['createdAt'])
                    item['date_published'] = dt.isoformat()
                    item['_timestamp'] = dt.timestamp()
                    item['_display_date'] = utils.format_display_date(dt)
                item['content_html'] = utils.add_embed('https://content.jwplatform.com/players/{}.html'.format(data['mediaId']))
                if 'embed' not in args and 'summary' in item:
                    item['content_html'] += '<p>' + item['summary'] + '</p>'
                return item

    if 'embed' in args:
        item['content_html'] = utils.format_embed_preview(item)
        return item

    item['content_html'] = ''
    is_summary = False
    for block in screen_json['firstBlockPage']['sideLoadedBlocks']:
        if is_summary and block['__typename'] != 'TextBlock':
            item['content_html'] += '</div>'
            is_summary = False
        
        if block['__typename'] == 'TextBlock' and block.get('textRole'):
            if 'SUMMARY' in block['textRole']:
                if not is_summary:
                    item['content_html'] += '<div style="border:1px solid light-dark(#ccc,#333); border-radius:10px; padding:8px;">'
                    is_summary = True
            elif is_summary:
                item['content_html'] += '</div>'
                is_summary = False

            if block['textRole'] in ['ARTICLE_AUTHOR', 'ARTICLE_DATETIME']:
                continue
            elif block['textRole'] == 'ARTICLE_EXCERPT':
                item['content_html'] = '<p><em>' + block['styledText']['text'] + '</em></p>' + item['content_html']
            elif block['textRole'] == 'ARTICLE_BODY':
                if block['styledText']['textType'] == 'RESTRICTED_HTML':
                    item['content_html'] += block['styledText']['text']
                else:
                    item['content_html'] += '<p>' + block['styledText']['text'] + '</p>'
            elif block['textRole'] == 'ARTICLE_SUBHEADER':
                if block['styledText']['textType'] == 'RESTRICTED_HTML':
                    item['content_html'] += block['styledText']['text']
                else:
                    item['content_html'] += '<h2>' + block['styledText']['text'] + '</h2>'
            elif block['textRole'] == 'ARTICLE_SUMMARY_TITLE':
                if block['styledText']['textType'] == 'RESTRICTED_HTML':
                    item['content_html'] += block['styledText']['text']
                else:
                    item['content_html'] += '<h3>' + block['styledText']['text'] + '</h3>'
            elif block['textRole'] == 'ARTICLE_SUMMARY_ITEM':
                if block['styledText']['textType'] == 'RESTRICTED_HTML':
                    item['content_html'] += block['styledText']['text']
                else:
                    item['content_html'] += '<p>' + block['styledText']['text'] + '</p>'
            else:
                logger.warning('unhandled TextBlock role {} in {}'.format(block['textRole'], item['url']))
        elif block['__typename'] == 'ImageBlock':
            captions = []
            if block['image'].get('title'):
                captions.append(block['image']['title'])
            if block['image'].get('copyright'):
                captions.append(block['image']['copyright'])
            item['content_html'] += utils.add_image(block['image']['url'], ' | '.join(captions))
        elif block['__typename'] in ['DpgBannerBlock', 'DividerBlock', 'LinkBlock']:
            # TODO: skip all LinkBlocks?
            continue
        else:
            logger.warning('unhandled block type {} in {}'.format(block['__typename'], item['url']))

    return item
