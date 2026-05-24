package com.boxbuilder.workplanner.ui.taskdetail.components

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.boxbuilder.workplanner.data.model.Comment
import com.boxbuilder.workplanner.data.model.ProposalStatus
import dev.jeziellago.compose.markdowntext.MarkdownText

private const val INDENT_PER_LEVEL_DP = 16

/** Group comments by parentCommentId — null key holds roots. */
private fun buildThreadMap(comments: List<Comment>): Map<String?, List<Comment>> =
    comments.groupBy { it.parentCommentId }

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun CommentSection(
    comments: List<Comment>,
    onAddComment: (String, String?) -> Unit,
    onDeleteComment: (Comment) -> Unit,
    onApproveProposal: (String) -> Unit = {},
    onDenyProposal: (String, String) -> Unit = { _, _ -> },
    modifier: Modifier = Modifier
) {
    var topText by remember { mutableStateOf("") }
    var replyingTo by remember { mutableStateOf<String?>(null) }
    var replyText by remember { mutableStateOf("") }
    var commentToDelete by remember { mutableStateOf<Comment?>(null) }
    var proposalToDeny by remember { mutableStateOf<Comment?>(null) }

    val threadMap = buildThreadMap(comments)
    val roots = threadMap[null].orEmpty()

    Column(modifier = modifier) {
        Text(
            text = "Comments (${comments.size})",
            style = MaterialTheme.typography.titleSmall,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        if (roots.isEmpty()) {
            Text(
                text = "No comments yet",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(vertical = 8.dp)
            )
        } else {
            roots.forEach { root ->
                CommentTreeNode(
                    comment = root,
                    threadMap = threadMap,
                    depth = 0,
                    replyingTo = replyingTo,
                    replyText = replyText,
                    onChangeReplyText = { replyText = it },
                    onStartReply = { id ->
                        // Silent discard of any in-progress reply on switch.
                        replyingTo = id
                        replyText = ""
                    },
                    onCancelReply = {
                        replyingTo = null
                        replyText = ""
                    },
                    onSubmitReply = {
                        val text = replyText.trim()
                        val parent = replyingTo
                        if (text.isNotEmpty() && parent != null) {
                            onAddComment(text, parent)
                            replyText = ""
                            replyingTo = null
                        }
                    },
                    onLongPressDelete = { commentToDelete = it },
                    onApprove = { onApproveProposal(it.id) },
                    onDeny = { proposalToDeny = it }
                )
            }
        }

        // Bottom composer (chat convention) — multi-line, always available
        // for new top-level comments.
        HorizontalDivider(modifier = Modifier.padding(top = 12.dp, bottom = 8.dp))
        Composer(
            value = topText,
            onValueChange = { topText = it },
            onSend = {
                val text = topText.trim()
                if (text.isNotEmpty()) {
                    onAddComment(text, null)
                    topText = ""
                }
            },
            placeholder = "Add a comment…"
        )
    }

    // Delete confirmation dialog
    commentToDelete?.let { comment ->
        AlertDialog(
            onDismissRequest = { commentToDelete = null },
            title = { Text("Delete comment?") },
            text = { Text(comment.text) },
            confirmButton = {
                TextButton(onClick = {
                    onDeleteComment(comment)
                    commentToDelete = null
                }) { Text("Delete") }
            },
            dismissButton = {
                TextButton(onClick = { commentToDelete = null }) { Text("Cancel") }
            }
        )
    }

    // Deny reason dialog
    proposalToDeny?.let { proposal ->
        DenyReasonDialog(
            onConfirm = { reason ->
                onDenyProposal(proposal.id, reason)
                proposalToDeny = null
            },
            onDismiss = { proposalToDeny = null }
        )
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun CommentTreeNode(
    comment: Comment,
    threadMap: Map<String?, List<Comment>>,
    depth: Int,
    replyingTo: String?,
    replyText: String,
    onChangeReplyText: (String) -> Unit,
    onStartReply: (String) -> Unit,
    onCancelReply: () -> Unit,
    onSubmitReply: () -> Unit,
    onLongPressDelete: (Comment) -> Unit,
    onApprove: (Comment) -> Unit,
    onDeny: (Comment) -> Unit
) {
    val children = threadMap[comment.id].orEmpty()
    val isReplyingHere = replyingTo == comment.id
    val indent = (depth * INDENT_PER_LEVEL_DP).dp

    Column(modifier = Modifier.padding(start = indent)) {
        if (comment.isProposal) {
            ProposalCard(
                comment = comment,
                onLongClick = { onLongPressDelete(comment) },
                onApprove = { onApprove(comment) },
                onDeny = { onDeny(comment) }
            )
        } else {
            CommentCard(
                comment = comment,
                onLongClick = { onLongPressDelete(comment) }
            )
        }

        // Reply action row
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 2.dp, bottom = 4.dp),
            horizontalArrangement = Arrangement.End
        ) {
            TextButton(
                onClick = {
                    if (isReplyingHere) onCancelReply() else onStartReply(comment.id)
                }
            ) {
                Text(if (isReplyingHere) "Cancel reply" else "Reply")
            }
        }
    }

    // Recurse into children (indented one level deeper).
    children.forEach { child ->
        CommentTreeNode(
            comment = child,
            threadMap = threadMap,
            depth = depth + 1,
            replyingTo = replyingTo,
            replyText = replyText,
            onChangeReplyText = onChangeReplyText,
            onStartReply = onStartReply,
            onCancelReply = onCancelReply,
            onSubmitReply = onSubmitReply,
            onLongPressDelete = onLongPressDelete,
            onApprove = onApprove,
            onDeny = onDeny
        )
    }

    // Inline reply composer: rendered after the subtree, indented one level
    // deeper than the parent — so it visually sits where the new child will
    // land.
    if (isReplyingHere) {
        Box(
            modifier = Modifier.padding(
                start = ((depth + 1) * INDENT_PER_LEVEL_DP).dp,
                top = 4.dp,
                bottom = 8.dp
            )
        ) {
            Composer(
                value = replyText,
                onValueChange = onChangeReplyText,
                onSend = onSubmitReply,
                onCancel = onCancelReply,
                placeholder = "Write a reply…",
                autoFocus = true
            )
        }
    }
}

@Composable
private fun Composer(
    value: String,
    onValueChange: (String) -> Unit,
    onSend: () -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    onCancel: (() -> Unit)? = null,
    autoFocus: Boolean = false
) {
    val focusRequester = remember { FocusRequester() }

    LaunchedEffect(autoFocus) {
        if (autoFocus) {
            try {
                focusRequester.requestFocus()
            } catch (_: Exception) { /* not yet attached — first compose */ }
        }
    }

    Column(modifier = modifier.fillMaxWidth()) {
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            placeholder = { Text(placeholder) },
            modifier = Modifier
                .fillMaxWidth()
                .then(if (autoFocus) Modifier.focusRequester(focusRequester) else Modifier),
            minLines = 5,
            maxLines = 12,
            singleLine = false
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            if (onCancel != null) {
                TextButton(onClick = onCancel) { Text("Cancel") }
            }
            Spacer(modifier = Modifier.weight(1f))
            Button(
                onClick = onSend,
                enabled = value.isNotBlank()
            ) {
                Icon(
                    Icons.AutoMirrored.Filled.Send,
                    contentDescription = "Send",
                    modifier = Modifier.size(16.dp)
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text("Send")
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun CommentCard(
    comment: Comment,
    onLongClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(bottom = 4.dp)
            .combinedClickable(
                onClick = {},
                onLongClick = onLongClick
            ),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (comment.isAgentComment)
                MaterialTheme.colorScheme.tertiaryContainer
            else
                MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            if (comment.isAgentComment) {
                Text(
                    text = comment.createdBy,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onTertiaryContainer,
                    modifier = Modifier.padding(bottom = 4.dp)
                )
            }
            MarkdownText(
                markdown = comment.text,
                style = MaterialTheme.typography.bodyMedium
            )
            Text(
                text = formatDate(comment.createdAt),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier
                    .align(Alignment.End)
                    .padding(top = 4.dp)
            )
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ProposalCard(
    comment: Comment,
    onLongClick: () -> Unit,
    onApprove: () -> Unit,
    onDeny: () -> Unit
) {
    val status = comment.proposalStatus
    val borderColor = when (status) {
        ProposalStatus.APPROVED -> Color(0xFF4CAF50) // Green
        ProposalStatus.DENIED -> Color(0xFFF44336)   // Red
        ProposalStatus.PENDING -> Color(0xFFFFC107)   // Amber/Yellow
        null -> Color(0xFFFFC107)
    }
    val containerColor = when (status) {
        ProposalStatus.APPROVED -> Color(0xFFE8F5E9) // Light green
        ProposalStatus.DENIED -> Color(0xFFFFEBEE)   // Light red
        ProposalStatus.PENDING -> Color(0xFFFFF8E1)  // Light amber
        null -> Color(0xFFFFF8E1)
    }
    val statusLabel = when (status) {
        ProposalStatus.APPROVED -> "Approved"
        ProposalStatus.DENIED -> "Denied"
        ProposalStatus.PENDING -> "Pending"
        null -> "Pending"
    }
    val statusColor = borderColor
    val isPending = status == null || status == ProposalStatus.PENDING

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(bottom = 4.dp)
            .combinedClickable(
                onClick = {},
                onLongClick = onLongClick
            ),
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(2.dp, borderColor),
        colors = CardDefaults.cardColors(containerColor = containerColor)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Header row: badge + status
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // "Proposal" badge
                Card(
                    shape = RoundedCornerShape(4.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = borderColor
                    )
                ) {
                    Text(
                        text = "Proposal",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        color = Color.White,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp)
                    )
                }

                // Status label
                Text(
                    text = statusLabel,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.SemiBold,
                    color = statusColor
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Author (for agent proposals)
            if (comment.isAgentComment) {
                Text(
                    text = comment.createdBy,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(bottom = 4.dp)
                )
            }

            // Proposal text
            MarkdownText(
                markdown = comment.text,
                style = MaterialTheme.typography.bodyMedium
            )

            // Show feedback if present (for approved/denied proposals)
            if (!comment.proposalFeedback.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(4.dp))
                MarkdownText(
                    markdown = "**Feedback:** ${comment.proposalFeedback}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Date
            Text(
                text = formatDate(comment.createdAt),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier
                    .align(Alignment.End)
                    .padding(top = 4.dp)
            )

            // Approve / Deny buttons — only for pending proposals
            if (isPending) {
                Spacer(modifier = Modifier.height(8.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedButton(
                        onClick = onDeny,
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = Color(0xFFF44336)
                        ),
                        border = BorderStroke(1.dp, Color(0xFFF44336))
                    ) {
                        Icon(
                            Icons.Default.Close,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Deny")
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Button(
                        onClick = onApprove,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color(0xFF4CAF50)
                        )
                    ) {
                        Icon(
                            Icons.Default.CheckCircle,
                            contentDescription = null,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Approve")
                    }
                }
            }
        }
    }
}

@Composable
private fun DenyReasonDialog(
    onConfirm: (String) -> Unit,
    onDismiss: () -> Unit
) {
    var reason by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Deny Proposal") },
        text = {
            Column {
                Text(
                    text = "Provide a reason for denying this proposal (optional):",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
                OutlinedTextField(
                    value = reason,
                    onValueChange = { reason = it },
                    placeholder = { Text("Reason...") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 2,
                    maxLines = 4
                )
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(reason) }) {
                Text("Deny", color = Color(0xFFF44336))
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        }
    )
}

private fun formatDate(millis: Long): String {
    val sdf = java.text.SimpleDateFormat("MMM d, yyyy", java.util.Locale.getDefault())
    return sdf.format(java.util.Date(millis))
}
