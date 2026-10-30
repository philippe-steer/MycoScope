package fr.mycoscope

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import fr.mycoscope.data.Piezo
import fr.mycoscope.data.WeatherGrid
import fr.mycoscope.ui.MycoApp
import fr.mycoscope.ui.MycoTheme
import org.osmdroid.config.Configuration
import java.io.File

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val conf = Configuration.getInstance()
        conf.userAgentValue = "MycoScope/" + BuildConfig.VERSION_NAME + " (+https://github.com/philippe-steer/MycoScope)"
        conf.osmdroidBasePath = File(cacheDir, "osmdroid")
        conf.osmdroidTileCache = File(cacheDir, "osmdroid/tiles")
        WeatherGrid.cacheRoot = filesDir
        Piezo.load(this)
        setContent { MycoTheme { MycoApp() } }
    }
}
