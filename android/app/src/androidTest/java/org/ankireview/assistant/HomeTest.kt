package org.ankireview.assistant

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.assertIsDisplayed
import org.junit.Rule
import org.junit.Test

class HomeTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    @Test fun showsReadOnlyHomeWithoutAnkiInstallation() {
        compose.onNodeWithText("只读 · 本地优先").assertIsDisplayed()
        compose.onNodeWithText("AnkiDroid 未安装或官方接口不可用").assertIsDisplayed()
    }
}
