import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BarChart3, Target, Zap, Award, BookOpen, Trophy, Clock, Crown } from 'lucide-react';
import { api } from '../api/client';
import { formatRelativeTime } from '../utils/time';

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
          <div className="h-8 w-48 bg-gray-200 rounded" />
          <div className="grid md:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-24 bg-gray-200 rounded-2xl" />
            ))}
          </div>
          <div className="h-64 bg-gray-200 rounded-2xl" />
        </div>
      </div>
    );
  }

  if (error || !data?.user_stats) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="card p-8 text-center">
          <p className="text-gray-500">
            {error instanceof Error ? error.message : 'User not found'}
          </p>
        </div>
      </div>
    );
  }

  const { user_stats, module_stats, rank, total_users } = data;
  const accuracy =
    user_stats.total_answers > 0
      ? Math.round((user_stats.correct_answers / user_stats.total_answers) * 100)
      : 0;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div className="flex items-center gap-3">
        <BarChart3 className="h-7 w-7 text-blue-600" />
        <h1 className="text-2xl font-bold text-gray-900">
          {userId ? `${user_stats.username}'s Stats` : 'Your Stats'}
        </h1>
      </div>

      {rank > 0 && (
        <div className="rounded-2xl p-5 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 text-white shadow-lg">
          <div className="flex items-center gap-3">
            <Trophy className="h-6 w-6 text-yellow-200" />
            <p className="text-lg font-semibold">
              {userId
                ? `Ranked #${rank} out of ${total_users} players`
                : `You're ranked #${rank} globally out of ${total_users} players`}
            </p>
          </div>
        </div>
      )}

      {user_stats.last_answer_time && (
        <div className="rounded-2xl p-5 bg-gradient-to-r from-blue-500 via-cyan-500 to-teal-500 text-white shadow-lg">
          <div className="flex items-center gap-3">
            <Clock className="h-6 w-6 text-blue-100" />
            <p className="text-lg font-semibold">
              Last active {formatRelativeTime(user_stats.last_answer_time)} ago
            </p>
          </div>
        </div>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Target}
          label="Correct Answers"
          value={user_stats.correct_answers.toLocaleString()}
          color="text-emerald-600"
          bgColor="bg-emerald-50"
        />
        <StatCard
          icon={BookOpen}
          label="Total Answers"
          value={user_stats.total_answers.toLocaleString()}
          subtext={`${accuracy}% accuracy`}
          color="text-blue-600"
          bgColor="bg-blue-50"
        />
        <StatCard
          icon={Zap}
          label="Current Streak"
          value={user_stats.current_streak.toString()}
          color="text-amber-600"
          bgColor="bg-amber-50"
        />
        <StatCard
          icon={Crown}
          label="Best Streak"
          value={user_stats.max_streak.toString()}
          color="text-purple-600"
          bgColor="bg-purple-50"
        />
        <StatCard
          icon={Award}
          label="Approved Cards"
          value={user_stats.approved_cards.toString()}
          color="text-purple-600"
          bgColor="bg-purple-50"
        />
      </div>

      {module_stats && module_stats.length > 0 && (
        <div className="card p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-4">
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
                  className="p-4 bg-gray-50 rounded-xl"
                >
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-semibold text-gray-900">{stat.module_name}</h3>
                    <span className="text-sm text-gray-500 font-medium">
                      {moduleAccuracy}% accuracy
                    </span>
                  </div>

                  <div className="w-full bg-gray-200 rounded-full h-2 mb-3">
                    <div
                      className="bg-blue-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${moduleAccuracy}%` }}
                    />
                  </div>

                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <p className="text-gray-500">Correct</p>
                      <p className="text-emerald-600 font-semibold">
                        {stat.number_correct}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500">Total</p>
                      <p className="text-blue-600 font-semibold">
                        {stat.number_answered}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500">Streak</p>
                      <p className="text-amber-600 font-semibold flex items-center gap-1">
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
  bgColor,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  subtext?: string;
  color: string;
  bgColor: string;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-2 rounded-lg ${bgColor}`}>
          <Icon className={`h-5 w-5 ${color}`} />
        </div>
        <span className="text-sm font-medium text-gray-500">{label}</span>
      </div>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
      {subtext && <p className="text-sm text-gray-400 mt-1">{subtext}</p>}
    </div>
  );
}
