package fr.mycoscope.data

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/**
 * Mise à jour en arrière-plan (toutes les 3 h environ, réseau requis) de la météo de la
 * dernière zone consultée : à l'ouverture, la carte du jour est déjà à jour, même hors réseau.
 */
class WeatherWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val store = Store(applicationContext)
        if (!store.autoUpdate) return Result.success()
        val b = store.box ?: return Result.success()
        WeatherGrid.cacheRoot = applicationContext.filesDir
        val s = WeatherGrid.spacingFor(b[1] - b[0], b[3] - b[2])
        return runCatching { WeatherGrid.field(b[0], b[1], b[2], b[3], s) }
            .fold({ if (it.partial != null) Result.retry() else Result.success() }, { Result.retry() })
    }

    companion object {
        private const val NAME = "meteo-champignons"

        fun schedule(ctx: Context, on: Boolean) {
            val wm = WorkManager.getInstance(ctx)
            if (!on) { wm.cancelUniqueWork(NAME); return }
            val req = PeriodicWorkRequestBuilder<WeatherWorker>(3, TimeUnit.HOURS, 1, TimeUnit.HOURS)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            wm.enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.KEEP, req)
        }
    }
}
