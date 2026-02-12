import { TrendingUp, TrendingDown, Calendar, Sparkles, AlertCircle, ArrowRight, Zap, Brain, ChevronDown, LayoutDashboard, Send, MessageSquare } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

type TimeFrame = "7days" | "thisWeek" | "30days" | "thisMonth" | "90days" | "thisQuarter";

interface SavedDashboard {
  id: string;
  name: string;
  description: string;
  lastModified: string;
}

export function Dashboard() {
  const hasConnectedSources = localStorage.getItem("hasConnectedSources") === "true";
  const hasSkippedOnboarding = localStorage.getItem("hasSkippedOnboarding") === "true";
  const hasAIConfigured = localStorage.getItem("ai_api_key_openai") || localStorage.getItem("ai_api_key_anthropic") || localStorage.getItem("ai_api_key_google");

  const [timeframe, setTimeframe] = useState<TimeFrame>("30days");
  const [showTimeframeMenu, setShowTimeframeMenu] = useState(false);
  const [showDashboardMenu, setShowDashboardMenu] = useState(false);

  // Sample saved dashboards
  const savedDashboards: SavedDashboard[] = [
    { id: "default", name: "Default Dashboard", description: "Standard overview", lastModified: "2 hours ago" },
    { id: "executive", name: "Executive Summary", description: "High-level KPIs", lastModified: "Yesterday" },
    { id: "marketing", name: "Marketing Performance", description: "Campaign metrics", lastModified: "3 days ago" },
    { id: "sales", name: "Sales Analytics", description: "Revenue & conversions", lastModified: "1 week ago" },
  ];

  const [selectedDashboard, setSelectedDashboard] = useState<string>("default");

  // Show empty state if user skipped onboarding or has no connected sources
  if (!hasConnectedSources || hasSkippedOnboarding) {
    return <EmptyDashboard />;
  }

  const timeframeOptions = [
    { id: "7days" as TimeFrame, label: "Last 7 days", description: "Previous week" },
    { id: "thisWeek" as TimeFrame, label: "This week", description: "Monday - Today" },
    { id: "30days" as TimeFrame, label: "Last 30 days", description: "Previous month" },
    { id: "thisMonth" as TimeFrame, label: "This month", description: "Month to date" },
    { id: "90days" as TimeFrame, label: "Last 90 days", description: "Previous quarter" },
    { id: "thisQuarter" as TimeFrame, label: "This quarter", description: "Quarter to date" },
  ];

  const getTimeframeLabel = (tf: TimeFrame) => {
    return timeframeOptions.find(opt => opt.id === tf)?.label || "Last 30 days";
  };

  const getCurrentDashboard = () => {
    return savedDashboards.find(d => d.id === selectedDashboard) || savedDashboards[0];
  };

  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Overview</h1>
          <p className="text-gray-600">{getTimeframeLabel(timeframe)}</p>
        </div>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div className="relative">
            <button
              onClick={() => setShowTimeframeMenu(!showTimeframeMenu)}
              className="w-full sm:w-auto flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              <Calendar className="w-4 h-4 text-gray-700" />
              <span className="text-gray-600 text-sm">Period:</span>
              <span className="font-medium text-gray-900 truncate">{getTimeframeLabel(timeframe)}</span>
              <ChevronDown className="w-4 h-4 text-gray-700 ml-auto" />
            </button>

            {showTimeframeMenu && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowTimeframeMenu(false)}
                />
                <div className="absolute right-0 mt-2 w-72 bg-white rounded-lg shadow-lg border border-gray-200 z-20">
                  <div className="p-3 border-b border-gray-200">
                    <h3 className="font-semibold text-gray-900 text-sm">Select Time Period</h3>
                    <p className="text-xs text-gray-500 mt-0.5">Currently showing: {getTimeframeLabel(timeframe)}</p>
                  </div>
                  <div className="p-2">
                    {timeframeOptions.map((option) => (
                      <button
                        key={option.id}
                        onClick={() => {
                          setTimeframe(option.id);
                          setShowTimeframeMenu(false);
                        }}
                        className={`w-full text-left px-4 py-3 rounded-lg hover:bg-gray-50 transition-colors ${
                          timeframe === option.id ? "bg-blue-50 border border-blue-200" : ""
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <p className={`font-medium ${
                                timeframe === option.id ? "text-blue-900" : "text-gray-900"
                              }`}>
                                {option.label}
                              </p>
                              {timeframe === option.id && (
                                <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full font-medium">
                                  Active
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-gray-500 mt-0.5">{option.description}</p>
                          </div>
                          {timeframe === option.id && (
                            <div className="w-2 h-2 bg-blue-600 rounded-full flex-shrink-0 ml-2" />
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="relative">
            <button
              onClick={() => setShowDashboardMenu(!showDashboardMenu)}
              className="w-full sm:w-auto flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              <LayoutDashboard className="w-4 h-4 text-gray-700" />
              <span className="text-gray-600 text-sm">Dashboard:</span>
              <span className="font-medium text-gray-900 truncate">{getCurrentDashboard().name}</span>
              <ChevronDown className="w-4 h-4 text-gray-700 ml-auto" />
            </button>

            {showDashboardMenu && (
              <>
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setShowDashboardMenu(false)}
                />
                <div className="absolute right-0 mt-2 w-80 bg-white rounded-lg shadow-lg border border-gray-200 z-20">
                  <div className="p-3 border-b border-gray-200">
                    <h3 className="font-semibold text-gray-900 text-sm">Switch Dashboard</h3>
                    <p className="text-xs text-gray-500 mt-0.5">Currently viewing: {getCurrentDashboard().name}</p>
                  </div>
                  <div className="p-2">
                    {savedDashboards.map((dashboard) => (
                      <button
                        key={dashboard.id}
                        onClick={() => {
                          setSelectedDashboard(dashboard.id);
                          setShowDashboardMenu(false);
                        }}
                        className={`w-full text-left px-4 py-3 rounded-lg hover:bg-gray-50 transition-colors ${
                          selectedDashboard === dashboard.id ? "bg-blue-50 border border-blue-200" : ""
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <p className={`font-medium ${
                                selectedDashboard === dashboard.id ? "text-blue-900" : "text-gray-900"
                              }`}>
                                {dashboard.name}
                              </p>
                              {selectedDashboard === dashboard.id && (
                                <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full font-medium">
                                  Active
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-gray-500 mt-0.5">{dashboard.description}</p>
                            <p className="text-xs text-gray-400 mt-1">Last modified: {dashboard.lastModified}</p>
                          </div>
                          {selectedDashboard === dashboard.id && (
                            <div className="w-2 h-2 bg-blue-600 rounded-full flex-shrink-0 ml-2" />
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <MetricCard
          title="Total Revenue"
          value="$45,234"
          change="+12.5%"
          trend="up"
        />
        <MetricCard
          title="Ad Spend"
          value="$12,458"
          change="+8.2%"
          trend="up"
        />
        <MetricCard
          title="ROAS"
          value="3.63x"
          change="+3.7%"
          trend="up"
        />
        <MetricCard
          title="Orders"
          value="423"
          change="+8.3%"
          trend="up"
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <h2 className="font-semibold text-gray-900 mb-4">Revenue vs Ad Spend</h2>
        <div className="h-64 flex items-center justify-center text-gray-400">
          Chart visualization would go here
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Top Campaigns (Facebook Ads)</h2>
          <div className="space-y-3">
            <CampaignRow name="Summer Sale" roas="4.2x" />
            <CampaignRow name="Brand Awareness" roas="3.8x" />
            <CampaignRow name="Product Launch" roas="3.1x" />
          </div>
          <button className="text-blue-600 text-sm font-medium mt-4 hover:underline">
            View Details →
          </button>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Channel Performance</h2>
          <div className="space-y-3">
            <ChannelRow name="Facebook" amount="$8,234" percentage="66%" />
            <ChannelRow name="Google" amount="$3,124" percentage="25%" />
            <ChannelRow name="TikTok" amount="$1,100" percentage="9%" />
          </div>
          <button className="text-blue-600 text-sm font-medium mt-4 hover:underline">
            View Details →
          </button>
        </div>
      </div>

      {/* AI Insights Section - Positioned after campaigns for better free trial UX */}
      <div className="mt-6">
        {hasAIConfigured ? <AIInsightsSection /> : <AIInsightsCTA />}
      </div>
    </div>
  );
}

function EmptyDashboard() {
  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6">
      <div className="bg-gradient-to-br from-blue-50 to-purple-50 rounded-2xl border-2 border-dashed border-blue-300 p-6 sm:p-12 text-center mb-8">
        <div className="max-w-3xl mx-auto">
          <div className="text-6xl mb-6">📊</div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-4">
            Connect your data to see insights
          </h1>
          <p className="text-xl text-gray-600 mb-8">
            Your dashboard is ready! Connect your first data source to start tracking performance.
          </p>
          <Link
            to="/sources"
            className="inline-flex items-center gap-2 px-8 py-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-lg"
          >
            Connect Your First Data Source
          </Link>
        </div>
      </div>

      {/* Sample Report Preview */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">Here's what your dashboard will look like:</h2>
          <span className="px-3 py-1 bg-yellow-100 text-yellow-800 text-sm rounded-full font-medium">
            Sample Data
          </span>
        </div>
        <p className="text-gray-600 mb-6">This is example data to show you what's possible</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6 opacity-60">
        <MetricCard
          title="Total Revenue"
          value="$45,234"
          change="+12.5%"
          trend="up"
          isSample
        />
        <MetricCard
          title="Ad Spend"
          value="$12,458"
          change="+8.2%"
          trend="up"
          isSample
        />
        <MetricCard
          title="ROAS"
          value="3.63x"
          change="+3.7%"
          trend="up"
          isSample
        />
        <MetricCard
          title="Orders"
          value="423"
          change="+8.3%"
          trend="up"
          isSample
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 opacity-60">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Top Campaigns</h2>
          <div className="space-y-3">
            <CampaignRow name="Summer Sale" roas="4.2x" />
            <CampaignRow name="Brand Awareness" roas="3.8x" />
            <CampaignRow name="Product Launch" roas="3.1x" />
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Channel Performance</h2>
          <div className="space-y-3">
            <ChannelRow name="Facebook" amount="$8,234" percentage="66%" />
            <ChannelRow name="Google" amount="$3,124" percentage="25%" />
            <ChannelRow name="TikTok" amount="$1,100" percentage="9%" />
          </div>
        </div>
      </div>

      <div className="mt-8 bg-white rounded-xl border border-gray-200 p-8 text-center">
        <h3 className="text-xl font-bold text-gray-900 mb-3">Ready to see your real data?</h3>
        <p className="text-gray-600 mb-6">
          Connect your data sources in just a few clicks and start making data-driven decisions.
        </p>
        <Link
          to="/sources"
          className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
        >
          Get Started Now →
        </Link>
      </div>
    </div>
  );
}

function MetricCard({ title, value, change, trend, isSample }: { title: string; value: string; change: string; trend: "up" | "down"; isSample?: boolean }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 relative">
      {isSample && (
        <div className="absolute top-2 right-2">
          <span className="px-2 py-1 bg-yellow-100 text-yellow-700 text-xs rounded-full font-medium">
            Sample
          </span>
        </div>
      )}
      <p className="text-sm text-gray-600 mb-1">{title}</p>
      <p className="text-3xl font-bold text-gray-900 mb-2">{value}</p>
      <div className={`flex items-center gap-1 text-sm ${trend === "up" ? "text-green-600" : "text-red-600"}`}>
        {trend === "up" ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
        {change}
      </div>
    </div>
  );
}

function CampaignRow({ name, roas }: { name: string; roas: string }) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-gray-900">{name}</span>
      <div className="flex items-center gap-2">
        <span className="font-semibold text-gray-900">{roas}</span>
        <button className="text-blue-600 hover:underline">→</button>
      </div>
    </div>
  );
}

function ChannelRow({ name, amount, percentage }: { name: string; amount: string; percentage: string }) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-gray-900">{name}</span>
      <span className="text-gray-600">{amount} ({percentage})</span>
    </div>
  );
}

function AIInsightsSection() {
  const [question, setQuestion] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const [conversationHistory, setConversationHistory] = useState<Array<{
    type: "user" | "ai";
    message: string;
    timestamp: string;
    data?: any;
  }>>([
    {
      type: "ai",
      message: "Hi! I'm your AI analytics assistant. I can help you analyze your data and answer questions. Try asking me something like:",
      timestamp: "Just now"
    }
  ]);

  const suggestedQuestions = [
    "What are my top 5 products by revenue?",
    "Find the top 5 products vs cost to acquire",
    "Which campaigns have the best ROAS?",
    "Show me conversion rate trends by channel",
    "What's my customer acquisition cost breakdown?",
    "Which ad creatives are performing best?",
  ];

  const handleAskQuestion = () => {
    if (!question.trim()) return;

    setIsAsking(true);

    // Add user question to conversation
    const userMessage = {
      type: "user" as const,
      message: question,
      timestamp: "Just now"
    };

    setConversationHistory(prev => [...prev, userMessage]);
    setQuestion("");

    // Simulate AI response
    setTimeout(() => {
      let aiResponse = {
        type: "ai" as const,
        message: "",
        timestamp: "Just now",
        data: null as any
      };

      // Smart responses based on question content
      if (question.toLowerCase().includes("top") && question.toLowerCase().includes("product")) {
        aiResponse.message = "Here are your top 5 products by revenue and their customer acquisition costs:";
        aiResponse.data = {
          type: "table",
          headers: ["Product", "Revenue", "Orders", "CAC", "Profit Margin"],
          rows: [
            ["Wireless Headphones Pro", "$12,450", "234", "$18.50", "67%"],
            ["Smart Watch Ultra", "$9,820", "156", "$24.20", "58%"],
            ["Bluetooth Speaker", "$7,340", "312", "$12.80", "71%"],
            ["Fitness Tracker", "$5,920", "198", "$15.40", "64%"],
            ["USB-C Hub", "$4,680", "445", "$8.90", "75%"],
          ]
        };
      } else if (question.toLowerCase().includes("roas") || question.toLowerCase().includes("campaign")) {
        aiResponse.message = "Your top performing campaigns ranked by ROAS:";
        aiResponse.data = {
          type: "list",
          items: [
            { label: "Summer Sale - Facebook", value: "4.2x ROAS", detail: "$8,234 spend → $34,583 revenue", status: "success" },
            { label: "Brand Awareness - Google", value: "3.8x ROAS", detail: "$3,124 spend → $11,871 revenue", status: "success" },
            { label: "Product Launch - TikTok", value: "3.1x ROAS", detail: "$1,100 spend → $3,410 revenue", status: "warning" },
          ]
        };
      } else if (question.toLowerCase().includes("conversion") || question.toLowerCase().includes("channel")) {
        aiResponse.message = "Here's your conversion rate breakdown by channel over the last 30 days:";
        aiResponse.data = {
          type: "metrics",
          items: [
            { label: "Facebook Ads", value: "3.2%", change: "+0.4%", trend: "up" },
            { label: "Google Ads", value: "2.8%", change: "+0.2%", trend: "up" },
            { label: "TikTok Ads", value: "2.1%", change: "-0.5%", trend: "down" },
            { label: "Organic Search", value: "4.5%", change: "+0.8%", trend: "up" },
          ]
        };
      } else if (question.toLowerCase().includes("cac") || question.toLowerCase().includes("acquisition cost")) {
        aiResponse.message = "Your customer acquisition cost breakdown by channel:";
        aiResponse.data = {
          type: "table",
          headers: ["Channel", "Total Spend", "New Customers", "CAC", "LTV/CAC Ratio"],
          rows: [
            ["Facebook Ads", "$8,234", "412", "$19.99", "3.2x"],
            ["Google Ads", "$3,124", "156", "$20.03", "3.0x"],
            ["TikTok Ads", "$1,100", "78", "$14.10", "4.1x"],
          ]
        };
      } else if (question.toLowerCase().includes("creative") || question.toLowerCase().includes("ad creative")) {
        aiResponse.message = "Top performing ad creatives based on engagement and conversion:";
        aiResponse.data = {
          type: "list",
          items: [
            { label: "Video Ad - Summer Collection", value: "5.2% CTR", detail: "234 conversions, $12,450 revenue", status: "success" },
            { label: "Carousel - Product Showcase", value: "4.1% CTR", detail: "189 conversions, $9,820 revenue", status: "success" },
            { label: "Static Image - Sale Banner", value: "2.8% CTR", detail: "98 conversions, $4,680 revenue", status: "warning" },
          ]
        };
      } else {
        aiResponse.message = "I can help you analyze your data! Here are some insights based on your current metrics:";
        aiResponse.data = {
          type: "insights",
          items: [
            { icon: "📈", text: "Your overall ROAS is 3.6x, which is 20% above industry average" },
            { icon: "💰", text: "Total revenue is up 12.5% compared to last period" },
            { icon: "🎯", text: "Facebook Ads are your most profitable channel with 66% of total ad spend" },
            { icon: "⚠️", text: "TikTok conversion rate has dropped 23% - consider refreshing creatives" },
          ]
        };
      }

      setConversationHistory(prev => [...prev, aiResponse]);
      setIsAsking(false);
    }, 1500);
  };

  const askSuggestedQuestion = (suggestedQ: string) => {
    setQuestion(suggestedQ);
  };

  return (
    <div className="bg-gradient-to-br from-purple-50 to-blue-50 rounded-xl border border-purple-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purple-600 rounded-lg">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900">AI Analytics Assistant</h2>
            <p className="text-sm text-gray-600">Ask questions about your data in natural language</p>
          </div>
        </div>
        <Link
          to="/settings?tab=ai"
          className="text-sm text-purple-600 hover:underline font-medium"
        >
          Settings →
        </Link>
      </div>

      {/* Conversation History */}
      <div className="bg-white rounded-lg border border-gray-200 mb-4 max-h-96 overflow-y-auto">
        <div className="p-4 space-y-4">
          {conversationHistory.map((msg, idx) => (
            <div key={idx}>
              {msg.type === "ai" ? (
                <div className="flex gap-3">
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 bg-purple-600 rounded-full flex items-center justify-center">
                      <Sparkles className="w-4 h-4 text-white" />
                    </div>
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-gray-900">AI Assistant</span>
                      <span className="text-xs text-gray-500">{msg.timestamp}</span>
                    </div>
                    <div className="text-gray-700 mb-2">{msg.message}</div>

                    {msg.data?.type === "table" && (
                      <div className="mt-3 overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-gray-200">
                              {msg.data.headers.map((header: string, i: number) => (
                                <th key={i} className="text-left py-2 px-3 font-semibold text-gray-900">{header}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {msg.data.rows.map((row: string[], i: number) => (
                              <tr key={i} className="border-b border-gray-100">
                                {row.map((cell: string, j: number) => (
                                  <td key={j} className="py-2 px-3 text-gray-700">{cell}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {msg.data?.type === "list" && (
                      <div className="mt-3 space-y-2">
                        {msg.data.items.map((item: any, i: number) => (
                          <div key={i} className="flex items-start justify-between p-3 bg-gray-50 rounded-lg">
                            <div className="flex-1">
                              <div className="font-medium text-gray-900">{item.label}</div>
                              <div className="text-sm text-gray-600">{item.detail}</div>
                            </div>
                            <div className={`px-3 py-1 rounded-full text-sm font-semibold ${
                              item.status === "success" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"
                            }`}>
                              {item.value}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {msg.data?.type === "metrics" && (
                      <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {msg.data.items.map((item: any, i: number) => (
                          <div key={i} className="p-3 bg-gray-50 rounded-lg">
                            <div className="text-sm text-gray-600 mb-1">{item.label}</div>
                            <div className="flex items-center justify-between">
                              <span className="text-xl font-bold text-gray-900">{item.value}</span>
                              <span className={`text-sm flex items-center gap-1 ${
                                item.trend === "up" ? "text-green-600" : "text-red-600"
                              }`}>
                                {item.trend === "up" ? "↑" : "↓"} {item.change}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {msg.data?.type === "insights" && (
                      <div className="mt-3 space-y-2">
                        {msg.data.items.map((item: any, i: number) => (
                          <div key={i} className="flex items-start gap-2 p-3 bg-gray-50 rounded-lg">
                            <span className="text-xl">{item.icon}</span>
                            <span className="text-gray-700">{item.text}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex gap-3 justify-end">
                  <div className="bg-blue-600 text-white rounded-lg px-4 py-2 max-w-md">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold">You</span>
                      <span className="text-xs text-blue-100">{msg.timestamp}</span>
                    </div>
                    <div>{msg.message}</div>
                  </div>
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center text-white font-semibold">
                      U
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}

          {isAsking && (
            <div className="flex gap-3">
              <div className="flex-shrink-0">
                <div className="w-8 h-8 bg-purple-600 rounded-full flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-white animate-pulse" />
                </div>
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Suggested Questions */}
      {conversationHistory.length <= 1 && (
        <div className="mb-4">
          <p className="text-sm text-gray-600 mb-2">Suggested questions:</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {suggestedQuestions.map((sq, idx) => (
              <button
                key={idx}
                onClick={() => askSuggestedQuestion(sq)}
                className="text-left text-sm px-3 py-2 bg-white border border-purple-200 rounded-lg hover:bg-purple-50 text-purple-900 transition-colors"
              >
                💡 {sq}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Question Input */}
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="flex-1 relative">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAskQuestion()}
            placeholder="Ask anything about your data..."
            className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            disabled={isAsking}
          />
          <MessageSquare className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
        </div>
        <button
          onClick={handleAskQuestion}
          disabled={!question.trim() || isAsking}
          className="px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-medium disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {isAsking ? (
            <>
              <Sparkles className="w-5 h-5 animate-spin" />
              Analyzing...
            </>
          ) : (
            <>
              <Send className="w-5 h-5" />
              Ask
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function AIInsightsCTA() {
  return (
    <div className="bg-gradient-to-br from-purple-50 to-blue-50 rounded-xl border-2 border-dashed border-purple-300 p-4 sm:p-8">
      <div className="flex flex-col sm:flex-row items-start gap-4 sm:gap-6">
        <div className="flex-shrink-0">
          <div className="w-16 h-16 bg-gradient-to-br from-purple-600 to-blue-600 rounded-2xl flex items-center justify-center">
            <Sparkles className="w-8 h-8 text-white" />
          </div>
        </div>
        <div className="flex-1">
          <div className="flex flex-col sm:flex-row items-start justify-between mb-3 gap-2">
            <div>
              <h3 className="text-xl sm:text-2xl font-bold text-gray-900 mb-2">Unlock AI-Powered Insights</h3>
              <p className="text-gray-600 sm:text-lg mb-4">
                Get intelligent recommendations, anomaly detection, and predictive analytics by connecting your AI provider
              </p>
            </div>
            <span className="px-3 py-1 bg-purple-600 text-white rounded-full text-sm font-medium">
              Premium
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
            <div className="bg-white rounded-lg p-4 border border-purple-200">
              <div className="flex items-center gap-2 mb-2">
                <Zap className="w-5 h-5 text-orange-600" />
                <h4 className="font-semibold text-gray-900">Smart Recommendations</h4>
              </div>
              <p className="text-sm text-gray-600">
                Get actionable suggestions to improve your ROAS and campaign performance
              </p>
            </div>
            <div className="bg-white rounded-lg p-4 border border-purple-200">
              <div className="flex items-center gap-2 mb-2">
                <AlertCircle className="w-5 h-5 text-red-600" />
                <h4 className="font-semibold text-gray-900">Anomaly Detection</h4>
              </div>
              <p className="text-sm text-gray-600">
                Automatically detect unusual patterns and potential issues in your data
              </p>
            </div>
            <div className="bg-white rounded-lg p-4 border border-purple-200">
              <div className="flex items-center gap-2 mb-2">
                <Brain className="w-5 h-5 text-purple-600" />
                <h4 className="font-semibold text-gray-900">Predictive Analytics</h4>
              </div>
              <p className="text-sm text-gray-600">
                Forecast future trends and optimize your marketing strategy
              </p>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <Link
              to="/settings?tab=ai"
              className="inline-flex items-center gap-2 px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-medium"
            >
              <Sparkles className="w-5 h-5" />
              Connect AI Provider
              <ArrowRight className="w-5 h-5" />
            </Link>
            <div className="text-sm text-gray-600">
              Supports OpenAI, Anthropic Claude, and Google AI
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
