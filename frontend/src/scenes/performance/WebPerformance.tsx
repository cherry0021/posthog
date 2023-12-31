import './WebPerformance.scss'
import { LemonTag } from 'lib/lemon-ui/LemonTag/LemonTag'
import { PageHeader } from 'lib/components/PageHeader'
import { RecentPerformancePageView } from '~/types'
import { webPerformanceLogic, WebPerformancePage } from 'scenes/performance/webPerformanceLogic'
import { SceneExport } from 'scenes/sceneTypes'
import { urls } from 'scenes/urls'
import { useValues } from 'kea'
import { WebPerformanceWaterfallChart } from 'scenes/performance/WebPerformanceWaterfallChart'
import { IconPlay } from 'lib/lemon-ui/icons'
import { LemonButton, Link } from '@posthog/lemon-ui'
import { Query } from '~/queries/Query/Query'
import { NodeKind, RecentPerformancePageViewNode } from '~/queries/schema'
import { humanFriendlyDuration } from 'lib/utils'

/*
 * show histogram of pageload instead of table
 */

function WaterfallButton(props: { record: RecentPerformancePageView; onClick: () => void }): JSX.Element {
    return (
        <div>
            <LemonButton
                data-attr={`view-waterfall-button-${props.record.pageview_id}`}
                icon={<IconPlay />}
                type="secondary"
                size="small"
                to={urls.webPerformanceWaterfall(props.record)}
            >
                View waterfall chart
            </LemonButton>
        </div>
    )
}

const EventsWithPerformanceTable = (): JSX.Element => {
    return (
        <>
            <div className="pt-4 border-t" />
            <Query
                query={{
                    kind: NodeKind.DataTableNode,
                    source: {
                        kind: NodeKind.RecentPerformancePageViewNode,
                        dateRange: {
                            date_from: null,
                            date_to: null,
                        },
                    },
                    columns: [
                        'context.columns.page_url',
                        'context.columns.duration',
                        'timestamp',
                        'context.columns.waterfallButton',
                    ],
                    showReload: true,
                    showColumnConfigurator: false,
                    showExport: false,
                    showEventFilter: false,
                    showPropertyFilter: false,
                    showActions: false,
                    expandable: false,
                }}
                context={{
                    showOpenEditorButton: true,
                    columns: {
                        page_url: {
                            title: 'Page',
                            render: function RenderPageURL({
                                record,
                            }: {
                                record: Required<RecentPerformancePageViewNode>['response']['results'][0]
                            }) {
                                return record.page_url ? (
                                    <div className={'max-w-100 overflow-auto'}>{record.page_url}</div>
                                ) : (
                                    <>-</>
                                )
                            },
                        },
                        duration: {
                            title: 'Page load',
                            render: function RenderPageLoad({
                                record,
                            }: {
                                record: Required<RecentPerformancePageViewNode>['response']['results'][0]
                            }) {
                                return record.duration ? <>{humanFriendlyDuration(record.duration / 1000)}</> : <>-</>
                            },
                        },
                        waterfallButton: {
                            title: '',
                            render: function RenderWaterfallButton({
                                record,
                            }: {
                                record: Required<RecentPerformancePageViewNode>['response']['results'][0]
                            }) {
                                return <WaterfallButton record={record} onClick={() => console.log(record)} />
                            },
                        },
                    },
                }}
            />
        </>
    )
}

export const WebPerformance = (): JSX.Element => {
    const { currentPage } = useValues(webPerformanceLogic)

    return (
        <div className="web-performance">
            <PageHeader
                title={
                    <div className="flex items-center gap-2">
                        Web Performance
                        <LemonTag type="warning" className="uppercase">
                            Alpha
                        </LemonTag>
                    </div>
                }
                caption={
                    currentPage === WebPerformancePage.TABLE ? (
                        <div>
                            <p>
                                Shows page view events where performance information has been captured. Not all events
                                have all performance information.
                            </p>
                            <p>
                                To capture performance information you must be using posthog-js and set{' '}
                                <code>_capture_performance</code> to true. See the{' '}
                                <Link
                                    to="https://posthog.com/docs/integrate/client/js#config"
                                    disableClientSideRouting={true}
                                >
                                    config instructions in our handbook
                                </Link>
                            </p>
                        </div>
                    ) : null
                }
            />
            <div>
                {currentPage === WebPerformancePage.TABLE ? (
                    <EventsWithPerformanceTable />
                ) : currentPage === WebPerformancePage.WATERFALL_CHART ? (
                    <WebPerformanceWaterfallChart />
                ) : (
                    <>404?</>
                )}
            </div>
        </div>
    )
}

export const scene: SceneExport = {
    component: WebPerformance,
    logic: webPerformanceLogic,
    paramsToProps: () => ({ sceneUrl: urls.webPerformance() }),
}
