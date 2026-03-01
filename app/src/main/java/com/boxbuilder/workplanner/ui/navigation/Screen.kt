package com.boxbuilder.workplanner.ui.navigation

sealed class Screen(val route: String) {
    object TaskList : Screen("tasklist")
    object TaskDetail : Screen("taskdetail/{taskId}") {
        fun createRoute(taskId: String) = "taskdetail/$taskId"
    }
    object NewTask : Screen("taskdetail/new?parentId={parentId}") {
        fun createRoute(parentId: String? = null): String {
            return if (parentId != null) "taskdetail/new?parentId=$parentId"
            else "taskdetail/new"
        }
    }
    object Settings : Screen("settings")
}
