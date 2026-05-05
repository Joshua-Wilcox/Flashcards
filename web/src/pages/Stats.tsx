import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BarChart3, Target, Zap, Award, BookOpen } from 'lucide-react';
import { api } from '../api/client';

export default function Stats() {
  const { userId } = useParams();

  const { data, isLoading, error } = useQuery({
    queryKey: ['stats', userId],
    queryFn: () => (userId ? api.getUserStats(userId) : api.getStats()),
  });

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-48 bg-slate-700 rounded" />
          <div className="grid md:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-24 bg-slate-700 rounded-xl" />
            ))}
          </div>
          <div className="h-64 bg-slate-700 rounded-xl" />
        </div>
      </div>
    );
  }

  if (error || !data?.user_stats) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="card p-8 text-center">
          <p className="text-slate-400">
            {error instanceof Error ? error.message : 'User not found'}
          </p>
        </div>
      </div>
    );
  }

  const { user_stats, module_stats } = data;
  const accuracy =
    user_stats.total_answers > 0
      ? Math.round((user_stats.correct_answers / user_stats.total_answers) * 100)
      : 0;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center gap-3">
        <BarChart3 className="h-7 w-7 text-blue-500" />
        <h1 className="text-2xl font-bold text-white">
          {userId ? `${user_stats.username}'s Stats` : 'Your Stats'}
        </h1>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Target}
          label="Correct Answers"
          value={user_stats.correct_answers.toLocaleString()}
          color="text-green-400"
        />
        <StatCard
          icon={BookOpen}
          label="Total Answers"
          value={user_stats.total_answers.toLocaleString()}
          subtext={`${accuracy}% accuracy`}
          color="text-blue-400"
        />
        <StatCard
          icon={Zap}
          label="Current Streak"
          value={user_stats.current_streak.toString()}
          color="text-yellow-400"
        />
        <StatCard
          icon={Award}
          label="Approved Cards"
          value={user_stats.approved_cards.toString()}
          color="text-purple-400"
        />
      </div>

      {module_stats && module_stats.length > 0 && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-white mb-4">
            Performance by Module
          </h2>

          <div className="space-y-4">
            {module_stats.map((stat) => {
              const moduleAccuracy =
                stat.number_answered > 0
                  ? Math.round((stat.number_correct / stat.number_answered) * 100)
                  : 0;

              return (
                <div
                  key={stat.module_id}
                  className="p-4 bg-slate-900/50 rounded-lg"
                >
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-medium text-white">{stat.module_name}</h3>
                    <span className="text-sm text-slate-400">
                      {moduleAccuracy}% accuracy
                    </span>
                  </div>

                  <div className="w-full bg-slate-700 rounded-full h-2 mb-3">
                    <div
                      className="bg-blue-500 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${moduleAccuracy}%` }}
                    />
                  </div>

                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <p className="text-slate-400">Correct</p>
                      <p className="text-green-400 font-medium">
                        {stat.number_correct}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-400">Total</p>
                      <p className="text-blue-400 font-medium">
                        {stat.number_answered}
                      </p>
                    </div>
                    <div>
                      <p className="text-slate-400">Streak</p>
                      <p className="text-yellow-400 font-medium flex items-center gap-1">
                        {stat.current_streak > 0 && <Zap className="h-3 w-3" />}
                        {stat.current_streak}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  subtext,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  subtext?: string;
  color: string;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-3 mb-2">
        <Icon className={`h-5 w-5 ${color}`} />
        <span className="text-sm text-slate-400">{label}</span>
      </div>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
      {subtext && <p className="text-xs text-slate-500 mt-1">{subtext}</p>}
    </div>
  );
}
